import os, openai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("API_KEY")
base_url = os.getenv('BASE_URL')
llm_model = os.getenv("LLM_MODEL")

client = openai.OpenAI(
    api_key=api_key,
    base_url=base_url
)

chat = client.chat.completions.create(
    model=llm_model,
    messages=[
        {
            "role": "user",
            "content": "What is the administrative capital of India?"
        }
    ]
)

print(chat.choices[0].message.content)