import requests
import json
import time
from typing import Dict, List
from pathlib import Path

def test_medicine_parser_api(input_file: str, output_file: str):
    # API endpoints
    BASE_URL = "http://localhost:8000"
    AUTH_URL = f"{BASE_URL}/auth/token"
    BATCH_URL = f"{BASE_URL}/parse/batch"
    
    try:
        # Read input file
        with open(input_file, 'r') as f:
            medicines = json.load(f)
        
        print(f"Loaded {len(medicines)} medicines from {input_file}")
        
        # Get authentication token
        auth_response = requests.post(
            AUTH_URL,
            params={
                "username": "medProcessor",  # Replace with your username
                "password": "tt@2024"  # Replace with your password
            }
        )
        
        if auth_response.status_code != 200:
            raise Exception(f"Authentication failed: {auth_response.text}")
            
        token = auth_response.json()["access_token"]
        print("Successfully obtained authentication token")
        
        # Prepare headers for API request
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Prepare data for batch processing
        batch_data = {
            "medicines": medicines
        }
        
        # Send request to API
        print("Sending request to API...")
        response = requests.post(
            BATCH_URL,
            headers=headers,
            json=batch_data
        )
        
        if response.status_code != 200:
            raise Exception(f"API request failed: {response.text}")
            
        # Get results
        results = response.json()
        
        # Save results to output file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            
        print(f"Successfully processed {len(results['medicines'])} medicines")
        print(f"Results saved to: {output_file}")
        
        # Print sample of results
        print("\nSample output (first medicine):")
        print(json.dumps(results['medicines'][0], indent=2))
        
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found")
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in input file")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to API. Make sure the API server is running")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    input_file = "input_medicines.json"
    output_file = "api_output.json"
    
    test_medicine_parser_api(input_file, output_file)