import torch
import torch.nn as nn
from transformers import AutoModel, AutoTokenizer
from PIL import Image
import os

# --- 1. CONFIGURATION ---
MODEL_PATH = 'deepseek-ai/DeepSeek-OCR' # Must match training
HEAD_WEIGHTS_PATH = 'deepseek_classifier_head.pth' # The file created by the training script
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE = torch.bfloat16 # Must match the training dtype

# --- 2. MODEL DEFINITION ---
# We must redefine the class exactly as it was in the training script
# so PyTorch knows how to load the weights into the specific structure.
class DeepSeekClassifier(nn.Module):
    def __init__(self, base_model_name):
        super().__init__()
        
        # Load the base VLM
        print(f"Loading Backbone ({base_model_name})...")
        self.backbone = AutoModel.from_pretrained(
            base_model_name, 
            trust_remote_code=True, 
            _attn_implementation='flash_attention_2', 
            use_safetensors=True
        )
        self.backbone = self.backbone.to(DEVICE).to(DTYPE)
        
        # Freeze Backbone
        for param in self.backbone.parameters():
            param.requires_grad = False
            
        # Define the Head
        hidden_size = self.backbone.config.hidden_size
        self.classifier = nn.Linear(hidden_size, 2)
        self.classifier = self.classifier.to(DEVICE).to(DTYPE)

    def forward(self, input_ids, images, attention_mask=None):
        outputs = self.backbone(
            input_ids=input_ids, 
            images=images, 
            attention_mask=attention_mask, 
            output_hidden_states=True
        )
        last_hidden_state = outputs.last_hidden_state
        pooled_output = last_hidden_state.mean(dim=1) 
        logits = self.classifier(pooled_output)
        return logits

# --- 3. INFERENCE LOADER ---

def load_classifier():
    """
    Initializes the model and loads the custom trained head weights.
    """
    # 1. Initialize the architecture
    model = DeepSeekClassifier(MODEL_PATH)
    
    # 2. Load the trained head weights
    if os.path.exists(HEAD_WEIGHTS_PATH):
        print(f"Loading trained weights from {HEAD_WEIGHTS_PATH}...")
        # We only saved model.classifier.state_dict()
        model.classifier.load_state_dict(torch.load(HEAD_WEIGHTS_PATH, map_location=DEVICE))
    else:
        raise FileNotFoundError(f"Could not find {HEAD_WEIGHTS_PATH}. Did you run the training script?")
    
    model.eval() # Set to evaluation mode
    
    # 3. Load Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    
    return model, tokenizer

# --- 4. PREDICTION FUNCTION ---

def predict_page(model, tokenizer, image_path):
    """
    Returns (label, probability)
    label: 1 (Start Page) or 0 (Other)
    """
    # 1. Prepare Image
    try:
        pil_image = Image.open(image_path).convert('RGB')
    except Exception as e:
        print(f"Error opening image: {e}")
        return None, 0.0

    # 2. Prepare Prompt (Must match training prompt!)
    prompt = "<image>\nClassify this page."
    
    # 3. Tokenize
    inputs = tokenizer(
        prompt, 
        return_tensors="pt", 
    )
    
    input_ids = inputs.input_ids.to(DEVICE)
    attention_mask = inputs.attention_mask.to(DEVICE)
    
    # 4. Prepare Images 
    # DeepSeek expects a list of images usually
    images = [pil_image] 
    
    # 5. Inference
    with torch.no_grad():
        logits = model(input_ids, images, attention_mask)
        
        # Calculate Probabilities
        probs = torch.nn.functional.softmax(logits, dim=1)
        
        # Get the winner
        pred_label = torch.argmax(probs, dim=1).item()
        confidence = probs[0][pred_label].item()
        
    return pred_label, confidence

# --- 5. RUN ---

if __name__ == "__main__":
    # Load once
    model, tokenizer = load_classifier()
    
    # List of images to test
    test_images = [
        'your_test_image.jpg',
        'another_document_page.jpg'
    ]
    
    print("\n--- Starting Inference ---")
    
    for img_file in test_images:
        if not os.path.exists(img_file):
            print(f"File not found: {img_file}")
            continue
            
        label, conf = predict_page(model, tokenizer, img_file)
        
        class_name = "STARTING PAGE" if label == 1 else "Other Page"
        print(f"File: {img_file}")
        print(f"Prediction: [{label}] {class_name}")
        print(f"Confidence: {conf:.4f}")
        print("-" * 20)
