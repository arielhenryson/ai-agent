import asyncio
from typing import Dict, List, Any
from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
import uuid
from bson import ObjectId

from .agent.agent import Agent
from .db.mongo import db_manager
from .auth.auth import VerifyToken


# --- Application State (In-Memory) ---
THREAD_STATUS: Dict[str, Dict[str, Any]] = {}
RUNNING_TASKS: Dict[str, asyncio.Task] = {}


# --- Helper Function for Message Generation ---
async def generate_message_and_update(user_id: str, text: str, thread_id: str, agent: Agent):
    """
    CORRECTED: Accumulates content locally and uses '$set' to update the
    entire message content in the database on each chunk.
    """
    try:
        print(f"ASYNC STREAM: Started for thread {thread_id}...")
        thread_data = await db_manager.get_thread_with_messages(thread_id, user_id)
        message_history = thread_data.get("messages", [])[
            :-1] if thread_data else []

        # --- STEP 1: Create the initial, empty assistant message ---
        assistant_message_id = ObjectId()
        timestamp_dt = datetime.now(timezone.utc)

        initial_llm_msg_doc = {
            "_id": assistant_message_id,
            "role": "model",
            "user_id": "LLM_Assistant",
            "type": "text",
            "content": "",
            "timestamp": timestamp_dt
        }
        await db_manager.create_message(thread_id, initial_llm_msg_doc)

        # --- STEP 2: Stream content and update the message ---
        response_stream = agent.stream_response(
            user_text=text,
            thread_id=thread_id,
            user_id=user_id,
            history=message_history
        )

        full_response_content = ""  # This variable will accumulate the full text
        chunk_count = 0
        async for response_chunk in response_stream:
            chunk_count += 1

            # Handles non-streaming types like 'confirmation'
            if response_chunk.get("type") != "text" and chunk_count == 1:
                await db_manager.update_full_message(thread_id, assistant_message_id, response_chunk)
                if THREAD_STATUS.get(thread_id):
                    THREAD_STATUS[thread_id]["messages"].append({
                        "id": str(assistant_message_id),
                        "role": "model",
                        "user_id": "LLM_Assistant",
                        "type": response_chunk.get("type"),
                        "content": response_chunk.get("content"),
                        "timestamp": timestamp_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
                        "isChunk": False
                    })
                break

            # FIXED: Accumulate content and use the correct DB update function
            content_piece = response_chunk.get("content", "")
            full_response_content += content_piece  # Append chunk to the full string

            # Update the DB with the *entire* accumulated message content
            await db_manager.update_message_content(thread_id, assistant_message_id, full_response_content)

            # Send only the small chunk to the UI for a live effect
            if THREAD_STATUS.get(thread_id):
                client_chunk = {
                    "id": str(assistant_message_id),
                    "content": content_piece,
                    "isChunk": True
                }
                THREAD_STATUS[thread_id]["messages"].append(client_chunk)

        print(f"ASYNC STREAM: Finished for thread {thread_id}.")

    except asyncio.CancelledError:
        print(f"ASYNC STREAM: Cancelled for thread {thread_id}.")
        raise

    except Exception as e:
        print(f"ASYNC STREAM: ERROR for thread {thread_id} - {e}")
        error_timestamp = datetime.now(timezone.utc)
        error_message_text = "Sorry, an error occurred while processing your request. Please try again."
        error_msg_doc = {
            "_id": ObjectId(),
            "role": "error",
            "type": "error",
            "user_id": "System",
            "content": error_message_text,
            "timestamp": error_timestamp
        }
        await db_manager.create_message(thread_id, error_msg_doc)
        if THREAD_STATUS.get(thread_id):
            THREAD_STATUS[thread_id]["messages"].append({
                "id": str(error_msg_doc["_id"]),
                "role": "error",
                "type": "error",
                "user_id": "System",
                "content": error_msg_doc["content"],
                "timestamp": error_msg_doc["timestamp"].strftime('%Y-%m-%dT%H:%M:%SZ')
            })
    finally:
        if THREAD_STATUS.get(thread_id):
            THREAD_STATUS[thread_id]["waitingForResponse"] = False
        RUNNING_TASKS.pop(thread_id, None)
        print(f"ASYNC STREAM: Cleaned up for thread {thread_id}.")


# --- FastAPI App Setup (No changes below this line) ---
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
async def start_new_chat(data: Dict[str, str] = Body(...), token_payload: Dict = Depends(token_verifier.verify)):
    user_id = token_payload.get("sub")
    initial_text = data.get("text")
    if not initial_text:
        raise HTTPException(
            status_code=400, detail="Message 'text' is required.")

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
        user_id, initial_text, new_thread_id, ai_agent))
    RUNNING_TASKS[new_thread_id] = task

    user_message_for_client = {
        "id": str(user_msg_doc["_id"]), "role": user_msg_doc["role"], "type": user_msg_doc["type"],
        "user_id": user_msg_doc["user_id"], "content": user_msg_doc["content"],
        "timestamp": user_msg_doc["timestamp"].strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    return {"thread_id": new_thread_id, "message": "Chat created...", "user_message": user_message_for_client}


@app.post("/api/chat/{thread_id}", status_code=202)
async def send_message_to_existing_chat(thread_id: str, data: Dict[str, str] = Body(...), token_payload: Dict = Depends(token_verifier.verify)):
    user_id = token_payload.get("sub")
    text = data.get("text")
    if not text:
        raise HTTPException(
            status_code=400, detail="Message 'text' is required.")

    timestamp_dt = datetime.now(timezone.utc)
    user_msg_doc = {
        "_id": ObjectId(), "role": "user", "type": "text", "user_id": user_id,
        "content": text, "timestamp": timestamp_dt
    }
    await db_manager.create_message(thread_id, user_msg_doc)

    THREAD_STATUS[thread_id] = {"waitingForResponse": True, "messages": []}
    task = asyncio.create_task(generate_message_and_update(
        user_id, text, thread_id, ai_agent))
    RUNNING_TASKS[thread_id] = task

    user_message_for_client = {
        "id": str(user_msg_doc["_id"]), "role": user_msg_doc["role"], "type": user_msg_doc["type"],
        "user_id": user_msg_doc["user_id"], "content": user_msg_doc["content"],
        "timestamp": user_msg_doc["timestamp"].strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    return {"thread_id": thread_id, "message": "Message received...", "user_message": user_message_for_client}


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
    status = THREAD_STATUS.get(thread_id, {})
    is_waiting = status.get("waitingForResponse", False)
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


@app.get("/api/chat/{thread_id}/poll")
def poll_chat_status(thread_id: str, token_payload: Dict = Depends(token_verifier.verify)):
    status = THREAD_STATUS.get(thread_id)
    if not status:
        return {"waitingForResponse": False, "messages": []}

    messages_to_send = status.get("messages", [])
    is_still_waiting = status.get("waitingForResponse", False)
    response = {"waitingForResponse": is_still_waiting,
                "messages": messages_to_send}

    if messages_to_send:
        status["messages"] = []
    if not is_still_waiting:
        THREAD_STATUS.pop(thread_id, None)
    return response


@app.post("/api/chat/{thread_id}/cancel", status_code=200)
def cancel_chat_generation(thread_id: str, token_payload: Dict = Depends(token_verifier.verify)):
    task = RUNNING_TASKS.get(thread_id)
    if not task:
        return {"message": f"No active task found for thread {thread_id} to cancel."}
    task.cancel()
    return {"message": f"Cancellation request sent for thread {thread_id}."}
