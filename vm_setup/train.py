import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from transformers import AutoModel, AutoTokenizer
from PIL import Image
import os

# --- 1. CONFIGURATION ---
BATCH_SIZE = 1 # VLMs are heavy; keep batch size low (1 or 2)
LEARNING_RATE = 1e-4
NUM_EPOCHS = 5
DEVICE = "cuda"
DTYPE = torch.bfloat16 # DeepSeek requires bfloat16 with Flash Attn

# Data Structure
example_data = [
    ('data/start_page_example_1.jpg', 1),
    ('data/middle_page_text_only.jpg', 0),
    ('data/invoice_random.jpg', 0),
    ('data/start_page_variation.jpg', 1),
    ('data/end_page_signatures.jpg', 0)
]

# --- 2. MODEL WRAPPER ---
class DeepSeekClassifier(nn.Module):
    def __init__(self, base_model_name):
        super().__init__()
        
        # Load the base VLM
        print("Loading DeepSeek Backbone...")
        self.backbone = AutoModel.from_pretrained(
            base_model_name, 
            trust_remote_code=True, 
            _attn_implementation='flash_attention_2', 
            use_safetensors=True
        )
        self.backbone = self.backbone.to(DEVICE).to(DTYPE)
        
        # FREEZE THE BACKBONE (The logic you requested)
        for param in self.backbone.parameters():
            param.requires_grad = False
            
        # Determine hidden size (usually 2048 or 4096 depending on model size)
        hidden_size = self.backbone.config.hidden_size
        
        # Append the new Classification Head
        # This is the ONLY layer that will be trained
        self.classifier = nn.Linear(hidden_size, 2)
        
        # Ensure head is in correct dtype/device
        self.classifier = self.classifier.to(DEVICE).to(DTYPE)

    def forward(self, input_ids, images, attention_mask=None):
        """
        We don't want text generation. We want the 'hidden_states' 
        representing the model's understanding of the image+prompt.
        """
        # Pass inputs to the frozen backbone
        # We assume the model expects 'images' or 'pixel_values' depending on exact architecture
        # DeepSeek-VL usually uses 'images' argument for the vision tower integration
        outputs = self.backbone(
            input_ids=input_ids, 
            images=images, 
            attention_mask=attention_mask, 
            output_hidden_states=True
        )
        
        # Extract the last hidden state: [Batch, Sequence_Length, Hidden_Dim]
        last_hidden_state = outputs.last_hidden_state
        
        # POOLING STRATEGY
        # We need to turn the sequence (text + image tokens) into one vector.
        # Simple approach: Mean pooling across the sequence dimension.
        # (Alternatively, we could grab the last token, but mean is often more stable for classification)
        pooled_output = last_hidden_state.mean(dim=1) 
        
        # Pass through our trainable classifier
        logits = self.classifier(pooled_output)
        
        return logits

# --- 3. DATASET ---
class VLMDataset(Dataset):
    def __init__(self, data_list, tokenizer, model):
        self.data_list = data_list
        self.tokenizer = tokenizer
        # We need the model's prepare logic (often inside the model or a processor)
        # DeepSeek-OCR/VL usually has a prepare function or uses standard transformers
        self.model_ref = model 

    def __len__(self):
        return len(self.data_list)

    def __getitem__(self, idx):
        img_path, label = self.data_list[idx]
        
        # 1. Prepare Image
        pil_image = Image.open(img_path).convert('RGB')
        
        # 2. Prepare Prompt
        # We give it a generic prompt so the VLM "looks" at the image
        prompt = "<image>\nClassify this page." 
        
        # 3. Process inputs using the model's built-in alignment logic if available
        # DeepSeek-VL repo usually suggests this pattern:
        prepare_inputs = self.model_ref.prepare_inputs_for_generation
        
        # Tokenize
        inputs = self.tokenizer(prompt, return_tensors="pt")
        
        # Specific DeepSeek image handling (assuming standard DeepSeek-VL behavior)
        # We need to load the image into the format the model expects (usually list of tensors)
        # Note: This part relies on DeepSeek's specific image transform. 
        # If 'aligner' or 'processor' is missing, we rely on the model's internal logic.
        
        # For this script, we assume the wrapper handles the heavy lifting, 
        # but we need to return the raw tensors.
        
        # Simplification for training script: 
        # We invoke the tokenizer and return the PIL image. 
        # The collate_fn will handle batching constraints.
        
        return {
            "pil_image": pil_image,
            "prompt": prompt,
            "label": torch.tensor(label, dtype=torch.long)
        }

def collate_fn(batch):
    """Custom collate to handle VLM variable image sizes"""
    tokenizer = global_tokenizer
    pil_images = [item['pil_image'] for item in batch]
    prompts = [item['prompt'] for item in batch]
    labels = torch.stack([item['label'] for item in batch])
    
    # Use the specific DeepSeek aligner/tokenizer logic
    # This prepares the inputs (input_ids, attention_mask, images list)
    inputs = tokenizer(
        prompts, 
        return_tensors="pt", 
        padding=True, 
        truncation=True
    )
    
    # DeepSeek-VL expects a specific list of images usually
    return inputs.input_ids, pil_images, inputs.attention_mask, labels


# --- 4. TRAINING ROUTINE ---

def train():
    model_name = 'deepseek-ai/DeepSeek-OCR'
    
    # Initialize Tokenizer globally for the dataset
    global global_tokenizer
    global_tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    
    # Initialize Custom Model
    model = DeepSeekClassifier(model_name)
    
    # Define Optimizer
    # IMPORTANT: We only pass model.classifier.parameters() to the optimizer.
    # The backbone parameters are frozen and won't be updated.
    optimizer = optim.AdamW(model.classifier.parameters(), lr=LEARNING_RATE)
    criterion = nn.CrossEntropyLoss()
    
    # Setup Data
    dataset = VLMDataset(example_data, global_tokenizer, model.backbone)
    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, collate_fn=collate_fn)
    
    print("Starting Training (Fine-tuning Head Only)...")
    
    for epoch in range(NUM_EPOCHS):
        model.train()
        total_loss = 0
        correct = 0
        total = 0
        
        for batch_idx, (input_ids, pil_images, attn_mask, labels) in enumerate(dataloader):
            input_ids = input_ids.to(DEVICE)
            labels = labels.to(DEVICE)
            attn_mask = attn_mask.to(DEVICE)
            
            # DeepSeek usually expects a list of PIL images or tensors. 
            # The 'prepare_inputs' inside the model usually handles the PIL->Tensor conversion
            # providing we assume the model has 'aligner'. 
            # If strictly tensor is needed, we would transform here.
            # Assuming standard DeepSeek-VL input signature:
            
            optimizer.zero_grad()
            
            # Forward Pass through Frozen Backbone + Trainable Head
            logits = model(input_ids, pil_images, attn_mask)
            
            loss = criterion(logits, labels)
            
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            
            # Accuracy Calc
            preds = torch.argmax(logits, dim=1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)
            
            if batch_idx % 10 == 0:
                print(f"Epoch {epoch} Batch {batch_idx}: Loss {loss.item():.4f}")

        print(f"Epoch {epoch+1} Results -- Loss: {total_loss/len(dataloader):.4f} | Accuracy: {correct/total:.2%}")

    # Save ONLY the classifier head (small file, ~10KB)
    torch.save(model.classifier.state_dict(), "deepseek_classifier_head.pth")
    print("Training complete. Head weights saved.")

if __name__ == "__main__":
    train()
