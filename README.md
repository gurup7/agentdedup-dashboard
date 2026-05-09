Quick Deploy & Demo Instructions
Here's everything you need to get this running from scratch:

Step 1: Clone the repo
git clone https://github.com/gurup7/agentdedup-dashboard.git
cd agentdedup-dashboard
Step 2: Configure AWS credentials
aws configure
# Enter: Access Key, Secret Key, Region (us-east-1), Output (json)
Step 3: Seed demo data
pip install boto3 requests
python scripts/demo-reset.py
Step 4: Start the dashboard
cd dashboard
pip install -r requirements.txt
streamlit run app.py
Step 5: Open browser
http://localhost:8501
Step 6: Follow the demo cheat sheet
Open DEMO-CHEATSHEET.md and follow the 5 scenarios.

That's it. The AWS backend (Lambda, DynamoDB, API Gateway, Step Functions) is already deployed in account 553556337417 region us-east-1. The dashboard connects to it via the API URL in 
.env
.

If deploying to a NEW AWS account:

Edit 
config.env
 with the new account ID and region
Run python deploy/deploy-all.py
Update 
.env
 with the new API URL and key
Streamlit Cloud (public URL): https://agentdedup-dashboard-h4cbtgytg59pvuowqerkey.streamlit.app/
