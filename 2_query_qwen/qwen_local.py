from transformers import Qwen3VLMoeForConditionalGeneration, AutoProcessor

# default: Load the model on the available device(s)
model = Qwen3VLMoeForConditionalGeneration.from_pretrained(
    "Qwen/Qwen3-VL-235B-A22B-Instruct", dtype="auto", device_map="auto"
)

# We recommend enabling flash_attention_2 for better acceleration and memory saving, especially in multi-image and video scenarios.
# model = Qwen3VLMoeForConditionalGeneration.from_pretrained(
#     "Qwen/Qwen3-VL-235B-A22B-Instruct",
#     dtype=torch.bfloat16,
#     attn_implementation="flash_attention_2",
#     device_map="auto",
# )

processor = AutoProcessor.from_pretrained("Qwen/Qwen3-VL-235B-A22B-Instruct")

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "image": "/2_query_qwen/NL-UtHUA_337-7_469_0003.jpg",
            },
            {
                "type": "image",
                "image": "/2_query_qwen/NL-UtHUA_337-7_469_0004.jpg",
            },
            {
                "type": "image",
                "image": "/2_query_qwen/NL-UtHUA_337-7_469_0005.jpg",
            },
            {
                "type": "image",
                "image": "/2_query_qwen/NL-UtHUA_337-7_469_0006.jpg",
            },
            {"type": "text", "text": "Transcribe this inheritance document to .json with the following keys: name, date of death, assets, liabilities and net wealth, followed by a transcription of all assets, liabilities and their values."},
        ],
    }
]

# Preparation for inference
inputs = processor.apply_chat_template(
    messages,
    tokenize=True,
    add_generation_prompt=True,
    return_dict=True,
    return_tensors="pt"
)

# Inference: Generation of the output
generated_ids = model.generate(**inputs, max_new_tokens=128)
generated_ids_trimmed = [
    out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
]
output_text = processor.batch_decode(
    generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
)
print(output_text)
