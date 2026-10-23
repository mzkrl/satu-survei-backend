git clone https://github.com/mzkrl/satusurvey.git && cd satusurvey
cp .env.example .env   
docker compose up -d --build
curl http://100.78.253.70:8000/api/surveys/
