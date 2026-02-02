from pprint import pprint
import requests
import resend
from jinja2 import Environment, FileSystemLoader
import os
import random

resend.api_key = os.getenv('RESEND_API_KEY')

# Load templates from the `templates` folder
env = Environment(loader=FileSystemLoader("templates"))

def render_template(template_name: str, context: dict = {}):
    try:
        template = env.get_template(template_name)
        return template.render(context)
    except Exception as e:
        print(f"Template rendering error: {e}")
        return "<p>Error rendering template</p>"
    
def send_email(template, subject, to, context, from_email="onboarding@noreply.vaulta.digital"):
# def send_email(template="otp_input.html", subject="HELLO", context={"name":"Kweku", "subject":"Welcome Email"}):
    # context={"name":"Kweku", "subject":"Welcome Email"}
    print(type(context))
    pprint(context)
    html_content = render_template(template, {**context, "subject": subject})
    try:
        params: resend.Emails.SendParams = {
        "from": from_email,
        "to": to,
        "subject": subject,
        "html": html_content,
        }
        email: resend.Email = resend.Emails.send(params)
        return email
        # return jsonify(r)

    except Exception as e:
        print(f"API error occurred: {str(e)}")
        return None

def generate_otp():
    otp = str(random.randint(100000, 999999))
    return otp

def send_slack(message):
    # check to see if slack messaging is allowed
    # if os.getenv("ALLOW_SLACK_MESSAGING") == "False":
    #     return ApiResponse(data=None, message="Slack messaging is not allowed", code=response.status_code, status="Undelivered", success=False)
    try:
        print(f"Preparing to send Slack message: {message}")
        slack_data = {'text': message}
        print(f"Slack data payload: {slack_data}")
        # Send the message to Slack
        response = requests.post("https://hooks.slack.com/services/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", json=slack_data)
        print(f"Slack response status code: {response.status_code}")
        print(f"Slack response text: {response.text}")
        return response
    except Exception as e:
        print(f"Error sending Slack message: {e}")
        return False
    
def send_private_slack(message):
    # check to see if slack messaging is allowed
    # if os.getenv("ALLOW_SLACK_MESSAGING") == "False":
    #     return ApiResponse(data=None, message="Slack messaging is not allowed", code=response.status_code, status="Undelivered", success=False)
    try:
        slack_data = {'text': message}
        # Send the message to Slack
        response = requests.post("https://hooks.slack.com/services/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", json=slack_data)
        return response
    except Exception as e:
        print(e)
        return False