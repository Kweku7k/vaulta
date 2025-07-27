from pprint import pprint
import resend
from jinja2 import Environment, FileSystemLoader
import os

resend.api_key = os.getenv("RESEND_API_KEY")  # or hardcode for now

# resend.api_key = "re_CJCGn5Mk_CRLAg54vTBRx18qfF8VGQMf6"

# Load templates from the `templates` folder
env = Environment(loader=FileSystemLoader("templates"))

def render_template(template_name: str, context: dict = {}):
    try:
        template = env.get_template(template_name)
        return template.render(context)
    except Exception as e:
        print(f"Template rendering error: {e}")
        return "<p>Error rendering template</p>"

def send_email(email, subject, template="welcome.html", context={}):
    try:
        html_content = render_template(template, {**context, "subject": subject})

        response = resend.Emails.send({
            "from": "onboarding@resend.dev",
            "to": email,
            "subject": subject,
            "html": html_content
        })
        
        pprint.pprint(response)

        print(response)
        return response

    except Exception as e:
        print(f"API error occurred: {str(e)}")
        return None