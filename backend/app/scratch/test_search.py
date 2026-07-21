"""
backend/app/scratch/test_search.py — Verification script for Google Search Grounding.
"""
import os
import sys
from pathlib import Path

# Add backend directory to python path
sys.path.append(str(Path(__file__).parents[2]))

from dotenv import load_dotenv
load_dotenv()

from app.capabilities.search.search_tools import search_web

def main():
    print("Testing Google Search Grounding...")
    query = "Who won the latest Super Bowl and what was the score?"
    print(f"Query: {query}\n")
    
    result = search_web(query)
    
    print("--- Search Result ---")
    print(result)
    print("---------------------")

if __name__ == "__main__":
    main()
