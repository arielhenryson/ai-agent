import asyncio
from typing import Dict, List, Any
from fastapi import FastAPI, Depends, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
import uuid
from bson import ObjectId
import logging

from .agent.agent import Agent
from .db.mongo import db_manager
from .auth.auth import VerifyToken

logger = logging.getLogger(__name__)

# --- Application State (In-Memory) ---
THREAD_STATUS: Dict[str, Dict[str, Any]] = {}
RUNNING_TASKS: Dict[str, asyncio.Task] = {}


# --- HELPER FUNCTION ---
async def generate_message_and_update(user_id: str, text: str, thread_id: str, agent: Agent, global_context: str):
    """
    This function calls the agent to process a message.
    The agent (using LLM.run) is responsible for saving ALL messages
    (tool calls, tool responses, and final model response) to the database.

    This function no longer streams chunks to the in-memory THREAD_STATUS,
    as the /poll endpoint will now read directly from the database.
    """
    try:
        print(f"ASYNC TASK: Started for thread {thread_id}...")
        thread_data = await db_manager.get_thread_with_messages(thread_id, user_id)
        message_history = thread_data.get("messages", [])[
            :-1] if thread_data else []

        # --- STEP 1: Run the agent ---
        response_stream = agent.stream_response(
            user_text=text,
            thread_id=thread_id,
            user_id=user_id,
            history=message_history,
            global_context=global_context
        )

        # We must iterate the generator to make it execute
        async for _ in response_stream:
            # We don't need the chunk, because LLM.run already
            # saved the final message to the DB.
            pass

        print(f"ASYNC TASK: Finished for thread {thread_id}.")

    except asyncio.CancelledError:
        print(f"ASYC TASK: Cancelled for thread {thread_id}.")
        raise

    except Exception as e:
        print(f"ASYNC TASK: ERROR for thread {thread_id} - {e}")
        # Log the error to the database as a new message
        try:
            error_msg_doc = {
                "_id": ObjectId(),
                "role": "error",  # Use a special role
                "user_id": "System",
                "type": "text",
                "content": f"An error occurred while processing your request: {str(e)}",
                "timestamp": datetime.now(timezone.utc)
            }
            await db_manager.create_message(thread_id, error_msg_doc)
        except Exception as db_e:
            print(
                f"ASYNC TASK: FAILED TO LOG ERROR to DB for thread {thread_id} - {db_e}")

    finally:
        # --- STEP 2: Update status ---
        if THREAD_STATUS.get(thread_id):
            THREAD_STATUS[thread_id]["waitingForResponse"] = False
        RUNNING_TASKS.pop(thread_id, None)
        print(f"ASYNC TASK: Cleaned up for thread {thread_id}.")


# --- FastAPI App Setup ---
token_verifier = VerifyToken()
ai_agent = Agent()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    await db_manager.create_indexes()


@app.post("/api/chat", status_code=202)
async def start_new_chat(data: Dict[str, Any] = Body(...), token_payload: Dict = Depends(token_verifier.verify)):
    user_id = token_payload.get("sub")
    initial_text = data.get("text")
    if not initial_text:
        raise HTTPException(
            status_code=400, detail="Message 'text' is required.")

    final_global_context = await db_manager.get_global_context(user_id)

    new_thread_id = f"t-{uuid.uuid4().hex[:8]}"
    timestamp_dt = datetime.now(timezone.utc)

    user_msg_doc = {
        "_id": ObjectId(), "role": "user", "type": "text", "user_id": user_id,
        "content": initial_text, "timestamp": timestamp_dt
    }

    new_thread_doc = {
        "_id": new_thread_id, "user_id": user_id, "title": initial_text[:30],
        "last_message": initial_text[:100], "timestamp": timestamp_dt,
        "messages": [user_msg_doc]
    }
    await db_manager.create_thread(new_thread_doc)

    THREAD_STATUS[new_thread_id] = {"waitingForResponse": True, "messages": []}

    task = asyncio.create_task(generate_message_and_update(
        user_id, initial_text, new_thread_id, ai_agent, final_global_context))
    RUNNING_TASKS[new_thread_id] = task

    user_message_for_client = {
        "id": str(user_msg_doc["_id"]), "role": user_msg_doc["role"], "type": user_msg_doc["type"],
        "user_id": user_msg_doc["user_id"], "content": user_msg_doc["content"],
        "timestamp": user_msg_doc["timestamp"].strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    return {"thread_id": new_thread_id, "message": "Chat created...", "user_message": user_message_for_client}


@app.post("/api/chat/{thread_id}", status_code=202)
async def send_message_to_existing_chat(thread_id: str, data: Dict[str, Any] = Body(...), token_payload: Dict = Depends(token_verifier.verify)):
    user_id = token_payload.get("sub")
    text = data.get("text")
    if not text:
        raise HTTPException(
            status_code=400, detail="Message 'text' is required.")

    final_global_context = await db_manager.get_global_context(user_id)

    timestamp_dt = datetime.now(timezone.utc)
    user_msg_doc = {
        "_id": ObjectId(), "role": "user", "type": "text", "user_id": user_id,
        "content": text, "timestamp": timestamp_dt
    }
    await db_manager.create_message(thread_id, user_msg_doc)

    THREAD_STATUS[thread_id] = {"waitingForResponse": True, "messages": []}

    task = asyncio.create_task(generate_message_and_update(
        user_id, text, thread_id, ai_agent, final_global_context))
    RUNNING_TASKS[thread_id] = task

    user_message_for_client = {
        "id": str(user_msg_doc["_id"]), "role": user_msg_doc["role"], "type": user_msg_doc["type"],
        "user_id": user_msg_doc["user_id"], "content": user_msg_doc["content"],
        "timestamp": user_msg_doc["timestamp"].strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    return {"thread_id": thread_id, "message": "Message received...", "user_message": user_message_for_client}


# --- Global Context Endpoints ---

@app.get("/api/global-context")
async def get_global_context(token_payload: Dict = Depends(token_verifier.verify)):
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=403, detail="User ID not found in token.")

    context = await db_manager.get_global_context(user_id)
    return {"context": context}


@app.post("/api/global-context", status_code=200)
async def save_global_context(data: Dict[str, str] = Body(...), token_payload: Dict = Depends(token_verifier.verify)):
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=403, detail="User ID not found in token.")

    context = data.get("context")
    if context is None:
        raise HTTPException(
            status_code=400, detail="Request body must contain a 'context' key.")

    try:
        await db_manager.save_global_context(user_id, context)
        return {"message": "Global context saved successfully."}
    except Exception as e:
        print(f"Error saving global context: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to save global context.")

# --- Other Endpoints ---


@app.get("/api/threads", response_model=List[Dict[str, Any]])
async def get_user_threads(token_payload: Dict = Depends(token_verifier.verify)):
    user_id = token_payload.get("sub")
    return await db_manager.get_user_threads(user_id)


@app.get("/api/chat/{thread_id}")
async def get_chat_messages(thread_id: str, token_payload: Dict = Depends(token_verifier.verify)):
    user_id = token_payload.get("sub")
    thread_data = await db_manager.get_thread_with_messages(thread_id, user_id)
    if not thread_data:
        raise HTTPException(
            status_code=404, detail=f"Thread with ID '{thread_id}' not found.")

    messages = thread_data.get("messages", [])

    status = THREAD_STATUS.get(thread_id)
    is_waiting = False
    if status:
        is_waiting = status.get("waitingForResponse", False)
    elif thread_id in RUNNING_TASKS:
        is_waiting = True

    return {"messages": messages, "waitingForResponse": is_waiting}


@app.delete("/api/chat/{thread_id}", status_code=200)
async def delete_chat_thread(thread_id: str, token_payload: Dict = Depends(token_verifier.verify)):
    user_id = token_payload.get("sub")
    was_deleted = await db_manager.delete_thread(thread_id, user_id)
    if not was_deleted:
        raise HTTPException(
            status_code=404, detail="Thread not found or you do not have permission.")

    THREAD_STATUS.pop(thread_id, None)
    task = RUNNING_TASKS.pop(thread_id, None)
    if task:
        task.cancel()
    return {"message": f"Thread '{thread_id}' has been successfully deleted."}


# --- vvv NEW ENDPOINT vvv ---
@app.patch("/api/chat/{thread_id}/rename", status_code=200)
async def rename_chat_thread(
    thread_id: str,
    data: Dict[str, str] = Body(...),
    token_payload: Dict = Depends(token_verifier.verify)
):
    """
    Renames a specific chat thread.
    """
    user_id = token_payload.get("sub")
    new_title = data.get("title")

    if not new_title:
        raise HTTPException(
            status_code=400, detail="Request body must contain a 'title' key.")

    was_renamed = await db_manager.rename_thread(thread_id, user_id, new_title)

    if not was_renamed:
        # This could be because it wasn't found or the title was the same
        # We'll check if it exists to give a better error
        thread_data = await db_manager.get_thread_with_messages(thread_id, user_id)
        if not thread_data:
            raise HTTPException(
                status_code=404, detail="Thread not found or you do not have permission.")
        # If it was found, it means the title was just not modified (e.g., same title)

    return {"message": f"Thread '{thread_id}' has been successfully renamed."}
# --- ^^^ END OF NEW ENDPOINT ^^^ ---


@app.get("/api/chat/{thread_id}/poll")
async def poll_chat_status(
    thread_id: str,
    since_id: str | None = Query(None),
    token_payload: Dict = Depends(token_verifier.verify)
):
    """
    Polls for new messages and agent status.
    Reads agent-running status from in-memory.
    Reads new messages (tools, final) from the DB.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=403, detail="User ID not found in token.")

    status = THREAD_STATUS.get(thread_id)

    is_still_waiting = False
    if status:
        is_still_waiting = status.get("waitingForResponse", False)
    elif thread_id in RUNNING_TASKS:
        is_still_waiting = True

    db_messages = []

    logger.info(
        f"[Poll] Thread {thread_id}: Received poll request. since_id='{since_id}'")

    if since_id:
        try:
            # We assume db_manager.get_thread_with_messages returns
            # SERIALIZED messages (with 'id', not '_id')
            thread_data = await db_manager.get_thread_with_messages(thread_id, user_id)

            if thread_data:
                all_messages = thread_data.get("messages", [])
                logger.info(
                    f"[Poll] Thread {thread_id}: Found {len(all_messages)} total messages in DB.")

                if all_messages:
                    logger.info(
                        f"[Poll] Thread {thread_id}: Last msg id in DB is {all_messages[-1].get('id')}")

                # --- NEW LOGIC: Find the index of the message the client has ---
                found_index = -1
                for i, msg in enumerate(all_messages):
                    if msg.get("id") == since_id:
                        found_index = i
                        break

                if found_index != -1:
                    # Get all messages *after* that index
                    new_messages_from_db = all_messages[found_index + 1:]
                    logger.info(
                        f"[Poll] Thread {thread_id}: Found {len(new_messages_from_db)} new messages after index {found_index}.")

                    # Messages are already serialized, just extend the list
                    db_messages.extend(new_messages_from_db)

                else:
                    # This can happen if the client's state is out of sync
                    logger.warning(
                        f"[Poll] Thread {thread_id}: Could not find since_id '{since_id}' in message list. Returning 0 new messages.")

            else:
                logger.warning(
                    f"[Poll] Thread {thread_id}: No thread data found for this user.")

        except Exception as e:
            logger.error(
                f"[Poll] Thread {thread_id}: Error processing poll: {e}", exc_info=True)

    elif not since_id:
        logger.warning(
            f"[Poll] Thread {thread_id}: Poll request received with no since_id.")

    if not is_still_waiting:
        THREAD_STATUS.pop(thread_id, None)

    return {
        "waitingForResponse": is_still_waiting,
        "messages": db_messages
    }


@app.post("/api/chat/{thread_id}/cancel", status_code=200)
def cancel_chat_generation(thread_id: str, token_payload: Dict = Depends(token_verifier.verify)):
    task = RUNNING_TASKS.get(thread_id)
    if not task:
        return {"message": f"No active task found for thread {thread_id} to cancel."}
    task.cancel()
    return {"message": f"Cancellation request sent for thread {thread_id}."}
