import os
from dotenv import load_dotenv
import dashscope

load_dotenv()

# The following base_url is for the Singapore region. If you use a model in the Beijing region, replace the base_url with https://dashscope.aliyuncs.com/api/v1.
dashscope.base_http_api_url = 'https://dashscope-intl.aliyuncs.com/api/v1'

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "image": f"file://2_query_qwen/NL-UtHUA_337-7_469_0003.jpg",
            },
            {
                "type": "image",
                "image": f"file://2_query_qwen/NL-UtHUA_337-7_469_0004.jpg",
            },
            {
                "type": "image",
                "image": f"file://2_query_qwen/NL-UtHUA_337-7_469_0005.jpg",
            },
            {
                "type": "image",
                "image": f"file://2_query_qwen/NL-UtHUA_337-7_469_0006.jpg",
            },
            {"type": "text", 
                "text": "Transcribe this inheritance document to .json with the following keys: name, date of death, total assets, total liabilities and net wealth, followed by a description of all assets, all liabilities and their values."
    },],
    }
]


response = dashscope.MultiModalConversation.call(
    # The API keys for the Singapore and Beijing regions are different. To obtain an API key, visit https://www.alibabacloud.com/help/en/model-studio/get-api-key.
    # If you have not configured an environment variable, use your Model Studio API key to replace the following line with api_key="sk-xxx".
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen3-vl-235b-a22b-thinking",  # In this example, qwen3-vl-plus is used. You can change the model name as needed. For a list of models, see https://www.alibabacloud.com/help/model-studio/getting-started/models.
    messages=messages)

#print(response["output"]["choices"][0]["message"].content[0]["text"])
output = response['output']['choices'][0]['message']['content'][0]['text']
# write the output to a file
with open('2_query_qwen/qwen_api_output2.json', 'w') as f:
    f.write(output)
