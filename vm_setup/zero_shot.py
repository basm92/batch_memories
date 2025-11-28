from transformers import AutoModel, AutoTokenizer
import torch
import os

# Setup
os.environ["CUDA_VISIBLE_DEVICES"] = '0'
model_name = 'deepseek-ai/DeepSeek-OCR' # Or your specific path
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
model = AutoModel.from_pretrained(model_name, _attn_implementation='flash_attention_2', trust_remote_code=True, use_safetensors=True)
model = model.eval().cuda().to(torch.bfloat16)

# Define your 5-shot instructions (Textual descriptions of your shots)
# This teaches the model the logic without needing to upload 5 extra images.
five_shot_context = """
Classify if this image is a Starting Page (1) or Not (0). 
Here are 5 examples of the logic:
1. IF the page contains the text "Memorie van Aangifte van het recht van Successie" -> Output: 1
2. IF the page is about real estate -> Output: 0
3. IF the page lists assets and liabilities -> Output: 0
4. IF the page contains the text "Nadere Memorie" or "Suppletoire Memorie" -> Output: 0
5. IF the page contains Memorie van Successie van -> Output: 1
"""

# Construct the prompt
prompt = f"<image>\n<|grounding|>{five_shot_context}\nAnalyze the current image. Return ONLY '1' if it is a starting page of a Memorie van Successie, or '0' if it is not."

image_file = 'your_image.jpg'
output_path = 'your/output/dir'

# infer(self, tokenizer, prompt='', image_file='', output_path = ' ', base_size = 1024, image_size = 640, crop_mode = True, test_compress = False, save_results = False):

# Tiny: base_size = 512, image_size = 512, crop_mode = False
# Small: base_size = 640, image_size = 640, crop_mode = False
# Base: base_size = 1024, image_size = 1024, crop_mode = False
# Large: base_size = 1280, image_size = 1280, crop_mode = False

# Gundam: base_size = 1024, image_size = 640, crop_mode = True

# Run Inference
res = model.infer(
    tokenizer, 
    prompt=prompt, 
    image_file=image_file, 
    output_path=output_path, 
    base_size=1024, 
    image_size=640, 
    crop_mode=True, 
    save_results=False # We don't necessarily need to save the visual result
)

print(f"Classification Result: {res}")
