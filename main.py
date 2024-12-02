from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import uvicorn
from groq import Groq
import re
import json
import os
import time
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
import jwt
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from fastapi.responses import JSONResponse
from functools import lru_cache
from redis import asyncio as aioredis

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    filename='api.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Medicine Parser API",
    description="API for parsing medicine names using Groq",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key')
ALGORITHM = "HS256"

# Pydantic models
class TokenData(BaseModel):
    username: str
    exp: datetime

class Medicine(BaseModel):
    NM: str
    VPID: str

class ParsedMedicine(BaseModel):
    VPID: str
    original_name: str
    name: str
    strength: str
    formulation: str

class MedicineList(BaseModel):
    medicines: List[Medicine]

class ParsedMedicineList(BaseModel):
    medicines: List[ParsedMedicine]

# Redis setup
async def create_redis_pool():
    redis = await aioredis.from_url(
        f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', 6379)}/0",
        encoding="utf-8",
        decode_responses=True
    )
    return redis

# Authentication functions
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        token_data = TokenData(username=username, exp=payload.get("exp"))
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return token_data

class MedicineGroqParser:
    def __init__(self):
        self.client = Groq(
            api_key=os.getenv('GROQ_API_KEY')
        )
        self.model = "mixtral-8x7b-32768"
        
        self.strength_pattern = re.compile(
            r'(\d+(?:\.\d+)?)\s*(?:micrograms|mcg|mg|g|ml|%)/(?:\d+(?:\.\d+)?)?\s*(?:ml|l)?|(\d+(?:\.\d+)?)\s*(?:micrograms|mcg|mg|g|ml)',
            re.IGNORECASE
        )
        self.formulation_pattern = re.compile(
            r'(tablets?|capsules?|(?:pre-filled\s+)?syringes?|(?:transdermal\s+)?patches?|oral\s+solution|suspension|cream|ointment|injection|powder|liquid|ampoules?|bottles?)',
            re.IGNORECASE
        )

    @lru_cache(maxsize=1000)
    def extract_components(self, medicine_string: str) -> Dict:
        try:
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

            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert in parsing medical product names. Extract components accurately."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=200
            )

            try:
                response_text = completion.choices[0].message.content
                if response_text.startswith('```json'):
                    response_text = response_text[7:-3]
                result = json.loads(response_text)
                
                if not result.get('strength'):
                    strength_match = self.strength_pattern.search(medicine_string)
                    result['strength'] = strength_match.group(0) if strength_match else ""
                    
                if not result.get('formulation'):
                    formulation_match = self.formulation_pattern.search(medicine_string)
                    result['formulation'] = formulation_match.group(0) if formulation_match else ""
                
                return result
                
            except (json.JSONDecodeError, AttributeError) as e:
                logger.error(f"Error parsing Groq response: {str(e)}")
                return self.extract_components_regex(medicine_string)
            
        except Exception as e:
            logger.error(f"Error in Groq API call: {str(e)}")
            return self.extract_components_regex(medicine_string)

    def extract_components_regex(self, medicine_string: str) -> Dict:
        try:
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
        except Exception as e:
            logger.error(f"Error in regex parsing: {str(e)}")
            raise

# Initialize parser
parser = MedicineGroqParser()

# FastAPI startup and shutdown events
@app.on_event("startup")
async def startup():
    # Create Redis connection pool
    app.state.redis = await create_redis_pool()
    await FastAPILimiter.init(app.state.redis)

@app.on_event("shutdown")
async def shutdown():
    await app.state.redis.close()

# API endpoints
@app.get("/")
async def read_root():
    return {"message": "Welcome to Medicine Parser API"}

@app.post("/auth/token")
async def login(username: str, password: str):
    if username == os.getenv('API_USERNAME') and password == os.getenv('API_PASSWORD'):
        access_token = create_access_token({"sub": username})
        return {"access_token": access_token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/parse/{vpid}")
async def parse_single_medicine(
    request: Request,
    vpid: str, 
    name: str,
    token_data: TokenData = Depends(verify_token),
    rate_limit: None = Depends(RateLimiter(times=10, minutes=1))
):
    try:
        logger.info(f"Processing single medicine request: VPID={vpid}, name={name}")
        
        components = parser.extract_components(name)
        result = ParsedMedicine(
            VPID=vpid,
            original_name=name,
            name=components['name'],
            strength=components['strength'],
            formulation=components['formulation']
        )
        
        logger.info(f"Successfully processed medicine: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error processing medicine: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/parse/batch")
async def parse_medicine_list(
    medicine_list: MedicineList,
    token_data: TokenData = Depends(verify_token),
    rate_limit: None = Depends(RateLimiter(times=2, minutes=1))
):
    try:
        logger.info(f"Processing batch request with {len(medicine_list.medicines)} medicines")
        
        parsed_medicines = []
        for medicine in medicine_list.medicines:
            components = parser.extract_components(medicine.NM)
            parsed_medicine = ParsedMedicine(
                VPID=medicine.VPID,
                original_name=medicine.NM,
                name=components['name'],
                strength=components['strength'],
                formulation=components['formulation']
            )
            parsed_medicines.append(parsed_medicine)
            time.sleep(0.1)  # Rate limiting
            
        logger.info(f"Successfully processed batch of {len(parsed_medicines)} medicines")
        return ParsedMedicineList(medicines=parsed_medicines)
        
    except Exception as e:
        logger.error(f"Error processing batch: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception handler: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred"}
    )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)