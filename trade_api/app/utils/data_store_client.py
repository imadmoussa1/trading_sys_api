import pymongo
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from .config import Config


class DataStoreClient:
    _mongo_client = None
    _trade_database = None

    @staticmethod
    def mongo_client():
        if DataStoreClient._mongo_client is None:
            mongo_uri = open("/run/secrets/main_data_store_db_uri", "r").readline()
            DataStoreClient._mongo_client = MongoClient(mongo_uri)

        return DataStoreClient._mongo_client

    @staticmethod
    def is_database_connected():
        try:
            DataStoreClient.mongo_client().admin.command('ismaster')
            return True
        except ConnectionFailure:
            return False

    @staticmethod
    def trade_database():
        if DataStoreClient._trade_database is None:
            DataStoreClient._trade_database = DataStoreClient.mongo_client()[Config.trade_database_name()]
        return DataStoreClient._trade_database

    @staticmethod
    def trade_collection():
        return DataStoreClient.trade_database()[Config.trade_collection_name()]

    @staticmethod
    def create_index():
        index_name = 'title_index'
        if index_name not in DataStoreClient.trade_collection().index_information():
            return DataStoreClient.trade_collection().create_index([('title', pymongo.TEXT)], name=index_name, default_language='english')
