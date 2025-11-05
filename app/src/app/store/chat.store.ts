import { inject } from '@angular/core'
import { signalStore, withMethods, withState, patchState } from '@ngrx/signals'
import { ChatService } from '../services/chat/chat.service'
import { timer, switchMap, takeWhile, Subscription, EMPTY } from 'rxjs'

// --- Interfaces ---
export interface Thread {
  id: string
  title: string
  last_message: string
  timestamp: string
}
export interface Message {
  id: string
  user_id: string
  content: any
  timestamp: string
  role: string
  type: string
}
export interface CurrentChat {
  messages: Message[]
  threadId: string | null
  waitingForResponse: boolean
}

export interface ChatState {
  threads: Thread[]
  currentChat: CurrentChat
  isLoading: boolean
  globalContext: string
}

const initialState: ChatState = {
  threads: [],
  currentChat: { messages: [], threadId: null, waitingForResponse: false },
  isLoading: false,
  globalContext: '',
}

export interface GlobalContextResponse {
  context: string
}
export interface GlobalContextPayload {
  context: string
}

// Module-level variable to hold the polling subscription
let pollingSubscription: Subscription | null = null

export const ChatStore = signalStore(
  { providedIn: 'root' },
  withState(initialState),
  withMethods((store, chatService = inject(ChatService)) => {
    /**
     * Internal helper function to start polling for chat responses.
     */
    const startPolling = (threadId: string) => {
      // Stop any existing polling
      if (pollingSubscription) {
        pollingSubscription.unsubscribe()
      }

      pollingSubscription = timer(1000, 3000) // Poll every 3s after 1s delay
        .pipe(
          switchMap(() => {
            const messages = store.currentChat.messages()
            if (messages.length === 0) {
              console.error('Polling started but no messages are in state.')
              return EMPTY // Stop the stream
            }
            // Get the ID of the very last message to poll "since"
            const lastMessageId = messages[messages.length - 1].id
            return chatService.pollForMessages(threadId, lastMessageId)
          }),
          // Keep polling *while* waiting, and include the final emission (true)
          takeWhile((response) => response.waitingForResponse, true)
        )
        .subscribe({
          next: (response) => {
            if (response.messages && response.messages.length > 0) {
              // Append new messages (e.g., tool calls, final response)
              patchState(store, (state) => ({
                currentChat: {
                  ...state.currentChat,
                  messages: [
                    ...state.currentChat.messages,
                    ...response.messages,
                  ],
                },
              }))
            }

            if (!response.waitingForResponse) {
              // Polling is done, update state
              patchState(store, (state) => ({
                currentChat: {
                  ...state.currentChat,
                  waitingForResponse: false,
                },
              }))
              // Refresh the sidebar
              methods.loadAllThreads()
              // Clean up subscription
              pollingSubscription?.unsubscribe()
              pollingSubscription = null
            }
          },
          error: (err) => {
            console.error('Polling failed:', err)
            patchState(store, (state) => ({
              currentChat: { ...state.currentChat, waitingForResponse: false },
            }))
            pollingSubscription = null
          },
        })
    }

    const methods = {
      /**
       * Fetches the user's global context from the API.
       */
      async loadGlobalContext(): Promise<void> {
        try {
          const response = await chatService.getGlobalContext()
          if (response && typeof response.context === 'string') {
            patchState(store, { globalContext: response.context })
          } else {
            patchState(store, { globalContext: '' })
          }
        } catch (e) {
          console.error('Failed to load global context:', e)
          patchState(store, { globalContext: '' })
        }
      },

      /**
       * Saves the user's global context to the API.
       */
      async saveGlobalContext(context: string): Promise<void> {
        try {
          const payload: GlobalContextPayload = { context: context }
          await chatService.saveGlobalContext(payload.context)
          patchState(store, { globalContext: context })
        } catch (e) {
          console.error('Failed to save global context:', e)
        }
      },

      /**
       * Fetches all of the user's chat threads for the sidebar.
       */
      async loadAllThreads(): Promise<void> {
        try {
          const threads = await chatService.getThreads()
          patchState(store, { threads })
        } catch (e) {
          console.error('Failed to load threads:', e)
        }
      },

      /**
       * Clears the main chat window, returning to the new-chat screen.
       */
      clearCurrentChat(): void {
        if (pollingSubscription) {
          pollingSubscription.unsubscribe()
          pollingSubscription = null
        }
        patchState(store, {
          currentChat: {
            waitingForResponse: false,
            messages: [],
            threadId: null,
          },
        })
      },

      /**
       * Loads a specific chat thread's messages into the main window.
       */
      async loadChat(threadId: string) {
        try {
          // Stop any polling from a *previous* chat
          if (pollingSubscription) {
            pollingSubscription.unsubscribe()
            pollingSubscription = null
          }

          // --- FIX 1: Set isLoading to true at the root ---
          patchState(store, {
            isLoading: true,
            currentChat: { // Reset the chat
              messages: [], 
              threadId: threadId, 
              waitingForResponse: true 
            },
          })

          const chatData = await chatService.getChatMessages(threadId)

          // --- FIX 2: Set isLoading to false on success ---
          patchState(store, {
            isLoading: false, // <-- Set to false
            currentChat: {
              threadId: threadId,
              messages: chatData.messages,
              waitingForResponse: chatData.waitingForResponse,
            },
          })

          // If the chat is *already* waiting when we load it, start polling.
          if (chatData.waitingForResponse) {
            startPolling(threadId)
          }
        } catch (e) {
          // --- FIX 3: Set isLoading to false on error ---
          patchState(store, { isLoading: false }) 
          console.error(`Failed to load chat ${threadId}`, e)
        }
      },

      /**
       * Sends a new message, creating a new thread or adding to an existing one.
       */
      async sendMessage(newMessage: Partial<Message>): Promise<string | null> {
        const currentThreadId = store.currentChat().threadId
        const content = newMessage.content ?? ''
        if (!content) return null

        // Create a temporary message for optimistic UI
        const tempId = `temp-user-msg-${Date.now()}`
        patchState(store, (state) => ({
          currentChat: {
            ...state.currentChat,
            messages: [
              ...state.currentChat.messages,
              {
                ...newMessage,
                id: tempId,
                role: 'user',
                type: 'text',
                timestamp: new Date().toISOString(),
              } as Message,
            ],
            waitingForResponse: true,
          },
        }))

        try {
          if (!currentThreadId) {
            // --- Create NEW Thread ---
            const response = await chatService.startNewChat(content)
            patchState(store, (state) => ({
              currentChat: {
                ...state.currentChat,
                threadId: response.thread_id,
                // Replace temp message with the real one from the server
                messages: state.currentChat.messages.map((m: Message) =>
                  m.id === tempId ? response.user_message : m
                ),
              },
            }))
            // Now that state has the real message ID, start polling
            startPolling(response.thread_id)
            methods.loadAllThreads() // Refresh sidebar
            return response.thread_id // Return ID for navigation
          } else {
            // --- Add to EXISTING Thread ---
            const response = await chatService.sendMessage(currentThreadId, content)
            patchState(store, (state) => ({
              currentChat: {
                ...state.currentChat,
                // Replace temp message with the real one from the server
                messages: state.currentChat.messages.map((m: Message) =>
                  m.id === tempId ? response.user_message : m
                ),
              },
            }))
            // Now that state has the real message ID, start polling
            startPolling(currentThreadId)
            return null // No new thread ID to return
          }
        } catch (e) {
          console.error('Failed to send message:', e)
          patchState(store, (state) => ({
            currentChat: { ...state.currentChat, waitingForResponse: false },
          }))
          // You could add an error message to the chat here
          return null
        }
      },

      /**
       * Cancels the current in-progress chat generation.
       */
      async cancelRequest(): Promise<void> {
        // Stop polling immediately
        if (pollingSubscription && !pollingSubscription.closed) {
          pollingSubscription.unsubscribe()
          pollingSubscription = null
        }
        patchState(store, (state) => ({
          currentChat: {
            ...state.currentChat,
            waitingForResponse: false,
          },
        }))
        const threadId = store.currentChat().threadId
        if (threadId) {
          try {
            await chatService.cancelRequest(threadId)
          } catch (e) {
            console.error('Failed to send cancellation request to backend:', e)
          }
        }
      },

      /**
       * Deletes a thread from the sidebar.
       */
      async deleteThread(threadId: string): Promise<void> {
        try {
          // Optimistic update
          patchState(store, (state) => {
            const updatedThreads = state.threads.filter((t) => t.id !== threadId)
            // If we deleted the *current* chat, clear the main window
            if (state.currentChat.threadId === threadId) {
              return {
                threads: updatedThreads,
                currentChat: {
                  messages: [],
                  threadId: null,
                  waitingForResponse: false,
                },
              }
            }
            // Otherwise, just update the threads list
            return { threads: updatedThreads }
          })
          
          // Make the API call
          await chatService.deleteThread(threadId)
        } catch (e) {
          console.error(`Failed to delete thread ${threadId}:`, e)
          // On failure, reload threads to get correct state back
          methods.loadAllThreads()
        }
      },

      // --- vvv THIS IS THE NEW METHOD vvv ---
      /**
       * Renames a thread.
       */
      async renameThread(threadId: string, newTitle: string): Promise<void> {
        // 1. Get original title for potential rollback
        const originalThread = store.threads().find((t) => t.id === threadId)
        if (!originalThread) {
          console.error('Cannot rename: thread not found in store.')
          return
        }
        const originalTitle = originalThread.title

        // 2. Optimistic Update: Update the UI immediately
        patchState(store, (state) => ({
          threads: state.threads.map((t) =>
            t.id === threadId ? { ...t, title: newTitle } : t
          ),
        }))

        // 3. API Call
        try {
          await chatService.renameThread(threadId, newTitle)
          // Success! The optimistic update is now confirmed.
        } catch (e) {
          console.error(`Failed to rename thread ${threadId}:`, e)

          // 4. Rollback on failure
          patchState(store, (state) => ({
            threads: state.threads.map((t) =>
              t.id === threadId ? { ...t, title: originalTitle } : t
            ),
          }))
          // You could show an error toast here
        }
      },
      // --- ^^^ END OF NEW METHOD ^^^ ---
    }

    // Return all the public methods
    return methods
  })
)