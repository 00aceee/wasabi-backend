from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise ValueError("MONGO_URI environment variable is not set!")

client = MongoClient(mongo_uri)
db = client["marmudb"]

def get_db():
    return db
