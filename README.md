# Create .env file
touch .env

# Add these variables to .env
GROQ_API_KEY=your_groq_api_key
JWT_SECRET_KEY=your_jwt_secret_key
API_USERNAME=your_chosen_username
API_PASSWORD=your_chosen_password
REDIS_HOST=localhost
REDIS_PORT=6379


pip install fastapi uvicorn groq python-dotenv pydantic python-jose[cryptography] fastapi-limiter redis[hiredis] PyJWT
or 
install them from requirements.txt

# Start Redis server
sudo systemctl start redis-server

# Check if Redis is running
sudo systemctl status redis-server

if active then proceed to next step 

#Get Access Token
curl -X POST "http://localhost:8000/auth/token?username=your_username&password=your_password"

#API calls
# For single medicine
curl -X GET "http://localhost:8000/parse/12345?name=Medicine%20Name" \
-H "Authorization: Bearer your_token_here"

# For batch processing
curl -X POST "http://localhost:8000/parse/batch" \
-H "Authorization: Bearer your_token_here" \
-H "Content-Type: application/json" \
-d '{"medicines": [{"NM": "Medicine Name", "VPID": "12345"}]}'


# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc

# Incase if you want to monitor the API 
tail -f api.log
