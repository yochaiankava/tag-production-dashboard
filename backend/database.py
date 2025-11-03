from sqlalchemy import create_engine, Column, String, Date
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///data/tags.db"
Base = declarative_base()

class Tag(Base):
    __tablename__ = "tags"
    device_id = Column(String, primary_key=True)
    production_date = Column(Date)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)
