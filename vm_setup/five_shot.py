from transformers import AutoModel, AutoTokenizer
import torch
import os

# --- 1. SETUP ---
os.environ["CUDA_VISIBLE_DEVICES"] = '0'
model_name = 'deepseek-ai/DeepSeek-OCR'

print("Loading model...")
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = AutoModel.from_pretrained(model_name, _attn_implementation='flash_attention_2', trust_remote_code=True, use_safetensors=True)
model = model.eval().cuda().to(torch.bfloat16)
print("Model loaded.")

# --- 2. HELPER FUNCTIONS ---

def get_image_content(model, tokenizer, image_path):
    """
    Runs the model strictly to get the text content (OCR) of an example image.
    We need this because we can't pass 5 actual images into the context at once.
    """
    ocr_prompt = "<image>\n<|grounding|>Convert the document to markdown."
    
    res = model.infer(
        tokenizer, 
        prompt=ocr_prompt, 
        image_file=image_path, 
        output_path='./temp', # Dummy path, we just want the text return
        base_size=1024, 
        image_size=640, 
        crop_mode=True, 
        save_results=False,
        test_compress=False 
    )
    return res

def build_five_shot_context(model, tokenizer, examples):
    """
    Takes a list of tuples: [('path/to/img1.jpg', 1), ('path/to/img2.jpg', 0), ...]
    Returns a formatted string containing the text of these images and their labels.
    """
    print(f"Building context from {len(examples)} examples. This might take a moment...")
    context_str = "Here are examples of how to classify the document:\n\n"
    
    for i, (img_path, label) in enumerate(examples):
        print(f"Processing example {i+1}/{len(examples)}: {img_path}")
        
        # 1. Extract text from the example image
        full_text = get_image_content(model, tokenizer, image_path)
        
        # 2. Truncate text. 
        # Classification usually relies on headers/first paragraphs. 
        # Keeping it short (e.g., 400 chars) saves context window and reduces noise.
        short_text = full_text[:400].replace('\n', ' ') 
        
        context_str += f"Example {i+1} Text: \"{short_text}...\"\n"
        context_str += f"Example {i+1} Label: {label}\n\n"
        
    return context_str

def classify_target_image(model, tokenizer, target_image_path, context_string):
    """
    Feeds the target image + the text context to the model for a final decision.
    """
    # Construct the final prompt
    # We ask the model to read the target image, compare it to the context, and output 1 or 0.
    instruction = (
        "Instructions: Read the text in the current image. "
        "Compare it with the examples above. "
        "If it looks like a Starting Page (based on headers like 'Memorie', 'Aangifte'), return '1'. "
        "Otherwise return '0'. "
        "Return ONLY the number."
    )
    
    final_prompt = f"<image>\n<|grounding|>{context_string}\n{instruction}"
    
    print(f"Classifying target: {target_image_path}...")
    res = model.infer(
        tokenizer, 
        prompt=final_prompt, 
        image_file=target_image_path, 
        output_path='./output', 
        base_size=1024, 
        image_size=640, 
        crop_mode=True, 
        save_results=False
    )
    
    return res

# --- 3. USAGE ---

# A. Define your 5 shots (Image Path, Class Label)
# Replace these paths with your actual 5 example images
example_data = [
    ('data/start_page_example_1.jpg', 1),
    ('data/middle_page_text_only.jpg', 0),
    ('data/invoice_random.jpg', 0),
    ('data/start_page_variation.jpg', 1),
    ('data/end_page_signatures.jpg', 0)
]

# B. Build the textual context (Runs OCR on the examples once)
# You can generate this once and reuse 'five_shot_prompt' for many target images
five_shot_prompt = build_five_shot_context(model, tokenizer, example_data)

print("-" * 30)
print("Generated Context String:")
print(five_shot_prompt)
print("-" * 30)

# C. Classify a NEW image
target_image = 'your_image.jpg'
result = classify_target_image(model, tokenizer, target_image, five_shot_prompt)

print(f"Final Classification Result: {result}")
