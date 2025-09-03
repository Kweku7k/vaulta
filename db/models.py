from sqlalchemy import Column, Integer, String
from database import Base  # or wherever your Base = declarative_base() is defined

class Customer(Base):
    __tablename__ = 'customer'
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=True)
    signed_agreement_id = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    birth_date = Column(String, nullable=True)
    address = Column(String, nullable=True)
    tax_identification_number = Column(String, nullable=True)
    gov_id_image_front = Column(String, nullable=True)
    gov_id_image_back = Column(String, nullable=True)
    status = Column(String, nullable=True)

    