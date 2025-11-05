import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from bson import ObjectId
import sys
from datetime import datetime, timedelta, timezone
import logging

load_dotenv()

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

if not all([MONGO_URI, DB_NAME]):
    missing_vars = [var for var, val in [
        ("MONGO_URI", MONGO_URI), ("DB_NAME", DB_NAME)] if not val]
    print(
        f"🔴 Error: Missing required environment variable(s): {', '.join(missing_vars)}", file=sys.stderr)
    sys.exit(1)


class MongoManager:
    def __init__(self):
        self.client = AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[DB_NAME]
        self.threads_collection = self.db.get_collection("threads")
        self.sql_reports_cache = self.db.get_collection("sql_reports_cache")
        self.global_context_collection = self.db.get_collection(
            "global_context")
        print("MongoDB connection initialized (including threads, sql_reports_cache, and global_context).")

    @staticmethod
    def format_thread(thread: dict) -> dict:
        if not thread:
            return {}
        formatted_messages = [
            {
                "id": str(msg["_id"]),
                "role": msg.get("role"),
                "user_id": msg.get("user_id", "Unknown"),
                "type": msg.get("type", "text"),
                "content": msg.get("content", ""),
                "timestamp": msg["timestamp"].strftime('%Y-%m-%dT%H:%M:%SZ')
            } for msg in thread.get("messages", [])
        ]
        return {
            "id": thread["_id"],
            "title": thread["title"],
            "user_id": thread["user_id"],
            "timestamp": thread["timestamp"].strftime('%Y-%m-%dT%H:%M:%SZ'),
            "messages": formatted_messages
        }

    async def create_indexes(self):
        await self.threads_collection.create_index("user_id")
        await self.sql_reports_cache.create_index("db_path", unique=True)
        await self.global_context_collection.create_index("user_id", unique=True)
        print("MongoDB indexes have been created/verified.")

    async def create_thread(self, thread_doc: dict):
        await self.threads_collection.insert_one(thread_doc)

    async def create_message(self, thread_id: str, message_doc: dict):
        """Pushes a complete message document into a thread's messages array."""
        content = message_doc.get("content", "")
        last_message_summary = content if isinstance(
            content, str) else "Interactive Message"

        await self.threads_collection.update_one(
            {"_id": thread_id},
            {
                "$push": {"messages": message_doc},
                "$set": {
                    "last_message": last_message_summary[:100],
                    "timestamp": message_doc["timestamp"]
                }
            }
        )

    async def update_message_content(self, thread_id: str, message_id: ObjectId, new_content: str):
        """
        Updates the 'content' field of a specific embedded message.
        """
        filter_query = {"_id": thread_id, "messages._id": message_id}
        update_query = {"$set": {"messages.$.content": new_content}}

        try:
            update_result = await self.threads_collection.update_one(
                filter_query,
                update_query
            )
            if update_result.matched_count == 0:
                logger.warning(
                    f"DB_UPDATE_FAILED: No document matched the filter. "
                    f"thread_id='{thread_id}', message_id='{message_id}'"
                )
            elif update_result.modified_count == 0:
                logger.warning(
                    f"DB_UPDATE_NO_CHANGE: Document matched but was not modified. "
                    f"thread_id='{thread_id}', message_id='{message_id}'"
                )
            else:
                logger.info(
                    f"DB_UPDATE_SUCCESS: Successfully updated message. "
                    f"thread_id='{thread_id}', message_id='{message_id}'"
                )
        except Exception as e:
            logger.error(
                f"DB_UPDATE_ERROR: Exception during message content update for "
                f"thread_id='{thread_id}', message_id='{message_id}': {e}"
            )

    async def update_full_message(self, thread_id: str, message_id: ObjectId, full_message_payload: dict):
        """Updates an existing embedded message with a full payload (for non-streaming types)."""
        await self.threads_collection.update_one(
            {"_id": thread_id, "messages._id": message_id},
            {
                "$set": {
                    "messages.$.type": full_message_payload.get("type"),
                    "messages.$.content": full_message_payload.get("content"),
                }
            }
        )

    async def get_user_threads(self, user_id: str) -> list[dict]:
        cursor = self.threads_collection.find(
            {"user_id": user_id},
            projection={"messages": 0}
        ).sort("timestamp", -1)

        threads = []
        async for doc in cursor:
            threads.append({
                "id": doc["_id"],
                "title": doc["title"],
                "last_message": doc.get("last_message", ""),
                "timestamp": doc["timestamp"].strftime('%Y-%m-%dT%H:%M:%SZ')
            })
        return threads

    async def get_thread_with_messages(self, thread_id: str, user_id: str):
        thread_doc = await self.threads_collection.find_one({"_id": thread_id, "user_id": user_id})
        return self.format_thread(thread_doc)

    async def delete_thread(self, thread_id: str, user_id: str) -> bool:
        delete_result = await self.threads_collection.delete_one({"_id": thread_id, "user_id": user_id})
        return delete_result.deleted_count > 0

    # --- vvv NEW METHOD vvv ---
    async def rename_thread(self, thread_id: str, user_id: str, new_title: str) -> bool:
        """Updates the 'title' of a specific thread."""
        logger.info(
            f"Attempting to rename thread_id '{thread_id}' for user_id '{user_id}' to '{new_title}'")
        if not new_title:
            logger.warning("Rename attempt failed: new_title is empty.")
            return False

        update_result = await self.threads_collection.update_one(
            {"_id": thread_id, "user_id": user_id},
            {"$set": {"title": new_title}}
        )
        if update_result.matched_count == 0:
            logger.warning(
                f"Rename failed: No thread found with id '{thread_id}' for user '{user_id}'")
            return False

        logger.info(f"Successfully renamed thread_id '{thread_id}'")
        return update_result.modified_count > 0
    # --- ^^^ END OF NEW METHOD ^^^ ---

    async def get_global_context(self, user_id: str) -> str:
        """Retrieves the global context string for a specific user."""
        logger.info(
            f"Attempting to get global context for user_id: '{user_id}'")
        doc = await self.global_context_collection.find_one({"user_id": user_id})
        if doc:
            logger.info(f"Found global context for user_id: '{user_id}'")
            return doc.get("context", "")
        logger.info(f"No global context found for user_id: '{user_id}'")
        return ""

    async def save_global_context(self, user_id: str, context: str):
        """Saves (upserts) the global context string for a specific user."""
        logger.info(
            f"Attempting to save global context for user_id: '{user_id}'")
        try:
            await self.global_context_collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "context": context,
                        "user_id": user_id,  # Ensure user_id is set on upsert
                        "updated_at": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )
            logger.info(
                f"Successfully saved global context for user_id: '{user_id}'")
        except Exception as e:
            logger.error(
                f"Failed to save global context for user_id '{user_id}': {e}")
            raise

    # --- CACHING METHODS ---
    # ... (rest of the file is unchanged) ...
    async def cache_sql_report(self, db_path: str, report_content: str):
        """Saves or updates (upserts) a SQL explorer report in the cache."""
        try:
            logger.info(f"Attempting to write cache for db_path: '{db_path}'")
            await self.sql_reports_cache.update_one(
                {"db_path": db_path},
                {
                    "$set": {
                        "report_content": report_content,
                        "cached_at": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )
            logger.info(f"Successfully cached SQL report for: {db_path}")
        except Exception as e:
            logger.error(f"Failed to cache SQL report for {db_path}: {e}")

    async def get_cached_sql_report(self, db_path: str, max_age_days: int) -> str | None:
        """RetrieVes a cached SQL report if it's not older than max_age_days."""
        try:
            logger.info(f"Querying cache for db_path: '{db_path}'")
            cached_doc = await self.sql_reports_cache.find_one({"db_path": db_path})

            if not cached_doc:
                logger.info(
                    f"No cache document found for db_path: '{db_path}'")
                return None

            cached_time = cached_doc.get("cached_at")
            if not cached_time:
                logger.warning(
                    f"Cache document for '{db_path}' found, but it has no 'cached_at' field. Will regenerate.")
                return None

            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=timezone.utc)

            expiry_date = datetime.now(
                timezone.utc) - timedelta(days=max_age_days)

            if cached_time >= expiry_date:
                logger.info(
                    f"Found VALID cache for: {db_path}. Cached at: {cached_time}")
                return cached_doc.get("report_content")
            else:
                logger.warning(
                    f"Found an *EXPIRED* cache for {db_path}. Cached at: {cached_time} (Cutoff was: {expiry_date})")
                return None
        except Exception as e:
            logger.error(
                f"Error retrieving cached SQL report for {db_path}: {e}")
            return None


db_manager = MongoManager()
