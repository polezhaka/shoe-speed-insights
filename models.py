from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer)
    access_token = db.Column(db.String(255))
    refresh_token = db.Column(db.String(255))
    expires_at = db.Column(db.Integer)
    scope = db.Column(db.String(255))
    name = db.Column(db.String(100))  # New column for user's name
    shoes = db.Column(db.String(500))  # New column for shoe IDs and names

    def __repr__(self):
        return '<User %r>' % self.name

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey('user.athlete_id'))  # Update to match the foreign key in User
    activity_id = db.Column(db.Integer)
    activity_date = db.Column(db.DateTime)
    activity_type = db.Column(db.String(50))
    elapsed_time = db.Column(db.Integer)
    moving_time = db.Column(db.Integer)
    distance = db.Column(db.Float)
    average_speed = db.Column(db.Float)
    gear_id = db.Column(db.String(100))
    pace = db.Column(db.Float)
