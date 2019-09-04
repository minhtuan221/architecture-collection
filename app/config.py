import json


def read_config(file_name="config.json"):
    with open(file_name, 'r') as json_file:
        cfg = json.load(json_file)
    return cfg


json_config = read_config('./config.json')
development_key = 'dev'
production_key = 'prod'
private_key_file = './private.pem'
public_key_file = './public.pem'


class Config(object):
    """Base config, uses staging database server."""
    DEBUG = False
    TESTING = False
    DB_SERVER = '0.0.0.0'
    PORT = 5010
    DATABASE_URL = "sqlite:///./test.db"
    LOG_FOLDER = '/home/minhtuan/Documents/python-world/python-clean-architecture/logs'
    PRIVATE_KEY = open(private_key_file).read()
    PUBLIC_KEY = open(public_key_file).read()


class ProductionConfig(Config):
    """Uses production database server."""
    DB_SERVER = '0.0.0.0'
    PORT = json_config['PORT']
    DATABASE_URL = json_config['sqlalchemy.url']
    LOG_FOLDER = json_config['log-folder']


class DevelopmentConfig(Config):
    DB_SERVER = '0.0.0.0'
    DEBUG = True
    PORT = json_config['PORT']
    DATABASE_URL = json_config['sqlalchemy.url']


class TestingConfig(Config):
    DB_SERVER = 'localhost'
    DEBUG = True
    DATABASE_URL = 'sqlite:///:memory:'


config = {
    'default': Config,
    'develop': DevelopmentConfig,
    'production': ProductionConfig,
    'test': TestingConfig
}

cli_config = config['production']
