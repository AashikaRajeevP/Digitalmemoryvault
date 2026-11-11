import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

load_dotenv()
db = SQLAlchemy()

IS_VERCEL = os.getenv("VERCEL") == "1"

app = Flask(
    __name__,
    template_folder='templates',
    instance_path="/tmp/instance" if IS_VERCEL else None,
)

if IS_VERCEL and not os.getenv("DATABASE_URL"):
    raise RuntimeError(
        "DATABASE_URL is not set. Add the Neon PostgreSQL connection string "
        "to the Vercel project environment variables."
    )

app.secret_key = os.getenv("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "SECRET_KEY is not set. Add it to .env locally or to Vercel environment variables."
    )

database_url = os.getenv("DATABASE_URL", "sqlite:///memoryvault.db")

if database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
    database_url = "postgresql+psycopg2://" + database_url.split("://", 1)[1]

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True, "pool_recycle": 300}

db.init_app(app)


class User(db.Model):
    __tablename__ = 'users'

    uid = db.Column(db.Integer,primary_key=True)
    username = db.Column(db.String,nullable=False,unique=True)
    password = db.Column(db.String,nullable=False)

    def __repr__(self):
        return f'<User: {self.username}>'

class Memory(db.Model):
    __tablename__ = 'memories'

    mid = db.Column(db.Integer,primary_key=True)
    title = db.Column(db.String,nullable=False)
    message = db.Column(db.String,nullable=False)
    open_date=db.Column(db.Date,nullable=False)
    created_on = db.Column(db.Date,nullable=False)
    user_id= db.Column(db.Integer,db.ForeignKey('users.uid'),nullable=False)

    def __repr__(self):
        return f'<Memory: {self.title}>'


with app.app_context():
    db.create_all()

from routes import *

if __name__ == '__main__':
    app.run(debug=True)