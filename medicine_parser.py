import re
import json
from typing import List, Dict
from pathlib import Path
from groq import Groq
import os
from tqdm import tqdm
import time

class MedicineGroqParser:
    def __init__(self):
        # Initialize Groq client
        self.client = Groq(
            api_key=os.getenv('GROQ_API_KEY')
        )
        
        # Model name
        self.model = "mixtral-8x7b-32768"  # or "llama2-70b-4096"
        
        # Compile regex patterns for validation and backup
        self.strength_pattern = re.compile(
            r'(\d+(?:\.\d+)?)\s*(?:micrograms|mcg|mg|g|ml|%)/(?:\d+(?:\.\d+)?)?\s*(?:ml|l)?|(\d+(?:\.\d+)?)\s*(?:micrograms|mcg|mg|g|ml)',
            re.IGNORECASE
        )
        self.formulation_pattern = re.compile(
            r'(tablets?|capsules?|(?:pre-filled\s+)?syringes?|(?:transdermal\s+)?patches?|oral\s+solution|suspension|cream|ointment|injection|powder|liquid|ampoules?|bottles?)',
            re.IGNORECASE
        )

    def extract_components(self, medicine_string: str) -> Dict:
        """
        Extract medicine components using Groq API and regex patterns
        """
        try:
            # Create prompt for Groq
            prompt = f"""Given the medicine name "{medicine_string}", extract the following components:
1. Medicine name (without strength and formulation)
2. Strength (with units)
3. Formulation

Return the result in JSON format like this:
{{
    "name": "medicine name",
    "strength": "strength with units",
    "formulation": "formulation type"
}}

Be precise and only include the exact information present in the input."""

            # Make API call to Groq
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert in parsing medical product names. Extract components accurately."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,  # Use 0 for consistent results
                max_tokens=200
            )

            # Parse the response
            try:
                response_text = completion.choices[0].message.content
                # Extract JSON from the response
                response_text = response_text.strip()
                if response_text.startswith('```json'):
                    response_text = response_text[7:-3]  # Remove ```json and ``` if present
                result = json.loads(response_text)
                
                # Validate and clean results
                if not result.get('strength'):
                    strength_match = self.strength_pattern.search(medicine_string)
                    result['strength'] = strength_match.group(0) if strength_match else ""
                    
                if not result.get('formulation'):
                    formulation_match = self.formulation_pattern.search(medicine_string)
                    result['formulation'] = formulation_match.group(0) if formulation_match else ""
                
                return result
                
            except (json.JSONDecodeError, AttributeError) as e:
                print(f"Error parsing Groq response for '{medicine_string}': {str(e)}")
                return self.extract_components_regex(medicine_string)
            
        except Exception as e:
            print(f"Error processing '{medicine_string}' with Groq: {str(e)}")
            # Fallback to regex-only method
            return self.extract_components_regex(medicine_string)

    def extract_components_regex(self, medicine_string: str) -> Dict:
        """
        Fallback method using only regex patterns
        """
        strength_match = self.strength_pattern.search(medicine_string)
        strength = strength_match.group(0) if strength_match else ""

        formulation_match = self.formulation_pattern.search(medicine_string)
        formulation = formulation_match.group(0) if formulation_match else ""

        name = medicine_string
        if strength:
            name = name.replace(strength, "")
        if formulation:
            name = name.replace(formulation, "")
            
        name = re.sub(r'^Generic\s+', '', name)
        name = re.sub(r'\s+sterile\s+', ' ', name)
        name = re.sub(r'\s+', ' ', name)
        name = name.strip().rstrip(" -,.")

        return {
            "name": name,
            "strength": strength,
            "formulation": formulation
        }

    def process_medicine_list(self, medicines: List[Dict]) -> List[Dict]:
        """
        Process a list of medicines and extract components for each
        """
        processed_medicines = []
        
        # Add progress bar
        for medicine in tqdm(medicines, desc="Processing medicines"):
            components = self.extract_components(medicine['NM'])
            processed_medicine = {
                'VPID': medicine['VPID'],
                'original_name': medicine['NM'],
                'name': components['name'],
                'strength': components['strength'],
                'formulation': components['formulation']
            }
            processed_medicines.append(processed_medicine)
            time.sleep(0.1)  # Small delay to avoid rate limits
            
        return processed_medicines

def process_file(input_file: str, output_file: str) -> None:
    """
    Read medicines from input JSON file, process them, and save to output JSON file
    """
    try:
        # Check for API key
        if not os.getenv('GROQ_API_KEY'):
            raise ValueError("GROQ_API_KEY environment variable not set")
            
        # Read input file
        with open(input_file, 'r') as f:
            medicines = json.load(f)
        
        # Initialize parser and process medicines
        parser = MedicineGroqParser()
        processed_medicines = parser.process_medicine_list(medicines)
        
        # Create output directory if it doesn't exist
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save results to output file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(processed_medicines, f, indent=2, ensure_ascii=False)
            
        print(f"\nSuccessfully processed {len(medicines)} medicines.")
        print(f"Results saved to: {output_file}")
        
        # Print a sample of the results
        if processed_medicines:
            print("\nSample output:")
            print(json.dumps(processed_medicines[0], indent=2))
        
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in input file '{input_file}'.")
    except Exception as e:
        print(f"Error: An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    input_file = "input_medicines.json"
    output_file = "output_medicines.json"
    process_file(input_file, output_file)