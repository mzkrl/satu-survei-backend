git clone https://github.com/mzkrl/satu-survei-backend && cd satusurvey
cp .env.example .env   
docker compose up -d --build
curl http://100.78.253.70:8000/api/surveys/

main repo: https://github.com/zufar-irawan/satu_survey