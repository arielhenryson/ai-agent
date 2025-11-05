import { Injectable, inject } from '@angular/core'
import { ApiService } from '../api/api.service'
// Import the interface from the store
import { 
  Thread, 
  Message, 
  GlobalContextResponse 
} from '../../store/chat.store' 

export interface ChatThreadData {
    messages: Message[];
    waitingForResponse: boolean;
}
export interface ChatPostConfirmation {
    thread_id: string;
    message: string;
    user_message: Message;
}
export interface PollResponse {
    waitingForResponse: boolean;
    messages: Message[];
}
export interface DeleteThreadResponse {
    message: string;
}
// --- vvv NEW INTERFACE vvv ---
export interface RenameThreadResponse {
    message: string;
}
// --- ^^^ END OF NEW INTERFACE ^^^ ---
export interface CancelResponse {
    message: string;
}

@Injectable({ providedIn: 'root' })
export class ChatService {
  apiService = inject(ApiService)
  private baseUrl = 'http://localhost:8000/api' 

  async getThreads(): Promise<Thread[]> {
    return this.apiService.get<Thread[]>(`${this.baseUrl}/threads`)
  }

  async getChatMessages(threadId: string): Promise<ChatThreadData> {
    return this.apiService.get<ChatThreadData>(`${this.baseUrl}/chat/${threadId}`)
  }

  async startNewChat(text: string): Promise<ChatPostConfirmation> {
    return this.apiService.post<ChatPostConfirmation>(`${this.baseUrl}/chat`, { text })
  }

  async sendMessage(threadId: string, text: string): Promise<ChatPostConfirmation> {
    return this.apiService.post<ChatPostConfirmation>(`${this.baseUrl}/chat/${threadId}`, { text })
  }
  
  async pollForMessages(threadId: string, since_id: string): Promise<PollResponse> {
    // Append the since_id as a query parameter
    return this.apiService.get<PollResponse>(
      `${this.baseUrl}/chat/${threadId}/poll?since_id=${since_id}`
    )
  }

  async cancelRequest(threadId: string): Promise<CancelResponse> {
    return this.apiService.post<CancelResponse>(`${this.baseUrl}/chat/${threadId}/cancel`, {})
  }

  async deleteThread(threadId: string): Promise<DeleteThreadResponse> {
    return this.apiService.delete<DeleteThreadResponse>(`${this.baseUrl}/chat/${threadId}`)
  }
  
  // --- vvv NEW METHOD vvv ---
  async renameThread(threadId: string, newTitle: string): Promise<RenameThreadResponse> {
    return this.apiService.patch<RenameThreadResponse>(
      `${this.baseUrl}/chat/${threadId}/rename`, 
      { title: newTitle }
    )
  }
  // --- ^^^ END OF NEW METHOD ^^^ ---

  async getGlobalContext(): Promise<GlobalContextResponse> {
    return this.apiService.get<GlobalContextResponse>(`${this.baseUrl}/global-context`)
  }

  async saveGlobalContext(context: string): Promise<void> {
    await this.apiService.post<void>(`${this.baseUrl}/global-context`, { context })
  }
}