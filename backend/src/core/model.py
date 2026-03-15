from sqlalchemy import Column, Integer, String, Date, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base  # 변경됨
from sqlalchemy.sql import func              # 추가됨

Base = declarative_base()

class News(Base):
    __tablename__ = 'news'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, index=True)
    keyword = Column(String, index=True)
    title = Column(String)
    content = Column(Text)
    url = Column(String, unique=True, index=True)
    is_embedded = Column(Boolean, default=False, index=True)
    published_date = Column(Date, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())