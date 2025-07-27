from models import Customer

def get_customer_by_email(email, db):
    return db.query(Customer).filter(Customer.email == email).first()