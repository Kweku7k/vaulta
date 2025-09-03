from pprint import pprint
import resend
from jinja2 import Environment, FileSystemLoader
import os
import random

resend.api_key = "re_CJCGn5Mk_CRLAg54vTBRx18qfF8VGQMf6"

# Load templates from the `templates` folder
env = Environment(loader=FileSystemLoader("templates"))

def render_template(template_name: str, context: dict = {}):
    try:
        template = env.get_template(template_name)
        return template.render(context)
    except Exception as e:
        print(f"Template rendering error: {e}")
        return "<p>Error rendering template</p>"
    
def send_email(template, subject, to, context):
# def send_email(template="otp_input.html", subject="HELLO", context={"name":"Kweku", "subject":"Welcome Email"}):
    # context={"name":"Kweku", "subject":"Welcome Email"}
    print(type(context))
    pprint(context)
    html_content = render_template(template, {**context, "subject": subject})
    try:
        params: resend.Emails.SendParams = {
        "from": "onboarding@noreply.vaulta.digital",
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
    
