from sqlalchemy import Column, Integer, String, Date, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class News(Base):
    __tablename__ = 'news'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, index=True)
    keyword = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    published_date = Column(Date, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)