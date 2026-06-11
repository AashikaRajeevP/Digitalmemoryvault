from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()

app = Flask(__name__,template_folder='templates')
app.secret_key = "memoryvault-secret-key"
app.config['SQLALCHEMY_DATABASE_URI']='sqlite:///memoryvault.db'

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