import { Component, ElementRef, HostListener, inject, OnInit, OnDestroy, signal, ViewChild, QueryList, ViewChildren, AfterViewChecked } from '@angular/core'
import { CommonModule, Location } from '@angular/common'
import { FormsModule } from '@angular/forms'
import { Router, RouterLink, ActivatedRoute } from '@angular/router'
import { Subject } from 'rxjs'
import { takeUntil } from 'rxjs/operators'
import { ApiService } from '../../../services/api/api.service'
import { OpenIdService } from '../../../services/open-id/open-id.service'
// --- vvv IMPORT THREAD INTERFACE vvv ---
import { ChatStore, Thread } from '../../../store/chat.store'
// --- ^^^ IMPORT THREAD INTERFACE ^^^ ---
import { ConfirmDialogComponent } from '../../../components/confirm-dialog/confirm-dialog.component'
import { GlobalContextModalComponent } from '../../../components/global-context-modal/global-context-modal.component'
import { TimeAgoPipe } from '../../../pipes/time-ago.pipe'
import { MarkdownComponent } from "ngx-markdown"

@Component({
  templateUrl: 'chat.component.html',
  styleUrls: [ 'chat.component.css' ],
  imports: [
    CommonModule, 
    FormsModule, 
    RouterLink, 
    ConfirmDialogComponent, 
    GlobalContextModalComponent, 
    TimeAgoPipe, 
    MarkdownComponent
  ]
})
export class ChatComponent implements OnInit, OnDestroy, AfterViewChecked {
  router = inject(Router)
  apiService = inject(ApiService)
  chatStore = inject(ChatStore)
  openIdService = inject(OpenIdService)
  private activatedRoute = inject(ActivatedRoute)
  private location = inject(Location)

  isChatAreaHovered = signal(false)
  showSystemMessages = signal(false)
  isSidebarOpen = signal(true)
  messageContent = signal('')
  isUserMenuOpen = false
  openThreadMenuId = signal<string | null>(null)
  
  isConfirmDialogOpen = signal(false)
  threadToDeleteId = signal<string | null>(null)

  isGlobalContextModalOpen = signal(false)

  // --- vvv NEW SIGNALS FOR RENAMING vvv ---
  editingThreadId = signal<string | null>(null)
  editingThreadTitle = signal<string>('')
  // --- ^^^ END OF NEW SIGNALS ^^^ ---

  @ViewChild('messageInput') messageInput!: ElementRef<HTMLTextAreaElement>
  @ViewChild('userMenuButton') userMenuButton!: ElementRef
  @ViewChild('userMenu') userMenu!: ElementRef
  @ViewChildren('threadMenuButton') threadMenuButtons!: QueryList<ElementRef>
  @ViewChildren('threadMenu') threadMenus!: QueryList<ElementRef>
  @ViewChild('chatContainer') private chatContainer!: ElementRef<HTMLDivElement>

  private destroy$ = new Subject<void>()
  private shouldScrollToBottom = false

  ngOnInit(): void {
    this.chatStore.loadAllThreads()
    this.chatStore.loadGlobalContext() 
    
    this.activatedRoute.paramMap
      .pipe(takeUntil(this.destroy$))
      .subscribe(async (params) => {
        const id = params.get('id')
        if (id) {
          // --- vvv ADDED LOGIC vvv ---
          // If we are editing a thread and navigate away, cancel the edit
          if (this.editingThreadId()) {
            this.cancelRename()
          }
          // --- ^^^ END OF ADDED LOGIC ^^^ ---
          await this.chatStore.loadChat(id)
        } else {
          this.chatStore.clearCurrentChat()
        }
        this.shouldScrollToBottom = true
      })
  }
  
  ngAfterViewChecked(): void {
    if (this.shouldScrollToBottom) {
      this.scrollToBottom()
      this.shouldScrollToBottom = false
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next()
    this.destroy$.complete()
  }

  private scrollToBottom(): void {
    try {
      if (this.chatContainer && this.chatContainer.nativeElement) {
        this.chatContainer.nativeElement.scrollTop = this.chatContainer.nativeElement.scrollHeight
      }
    } catch (err) {
      console.error('Could not scroll to bottom:', err)
    }
  }

  toggleUserMenu(): void {
    this.isUserMenuOpen = !this.isUserMenuOpen
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (this.isUserMenuOpen) {
      const clickedOnButton = this.userMenuButton.nativeElement.contains(event.target)
      const clickedInsideMenu = this.userMenu.nativeElement.contains(event.target)
      if (!clickedOnButton && !clickedInsideMenu) {
        this.isUserMenuOpen = false
      }
    }
    
    if (this.openThreadMenuId()) {
        // --- vvv MODIFIED LOGIC vvv ---
        // Check if the click was on a button OR inside a menu
        const clickedOnButton = this.threadMenuButtons.some(btn => btn.nativeElement.contains(event.target))
        const clickedInsideMenu = this.threadMenus.some(menu => menu.nativeElement.contains(event.target))
        
        // If the click is NOT on a button and NOT in a menu, close the menu
        if (!clickedOnButton && !clickedInsideMenu) {
            this.openThreadMenuId.set(null)
        }
        // --- ^^^ END OF MODIFIED LOGIC ^^^ ---
    }
  }

  @HostListener('input')
  onInput(): void {
    this.adjustTextareaHeight()
  }

  adjustTextareaHeight(): void {
    if (this.messageInput && this.messageInput.nativeElement) {
      const textarea = this.messageInput.nativeElement
      textarea.style.height = 'auto'
      textarea.style.height = `${textarea.scrollHeight}px`
    }
  }

  handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      this.sendMessage()
    }
  }

  async sendMessage(): Promise<void> {
    const content = this.messageContent().trim()
    if (content) {
      this.shouldScrollToBottom = true

      const newThreadId = await this.chatStore.sendMessage({
        role: 'user',
        content: content,
      })

      this.messageContent.set('')
      
      if (newThreadId) {
        this.location.replaceState(`/chat/${newThreadId}`)
      }
      
      setTimeout(() => {
        this.adjustTextareaHeight()
        this.messageInput.nativeElement.focus()
      }, 0)
    }
  }
  
  cancelRequest(): void {
    this.chatStore.cancelRequest()
  }

  goToThread(threadId: string): void {
    // --- vvv ADDED LOGIC vvv ---
    // Do not navigate if we are renaming this thread
    if (this.editingThreadId() === threadId) {
      return
    }
    // --- ^^^ END OF ADDED LOGIC ^^^ ---
    this.router.navigate([`/chat/${threadId}`])
  }
  
  toggleThreadMenu(event: MouseEvent, threadId: string): void {
    event.stopPropagation()
    // --- vvv ADDED LOGIC vvv ---
    // Don't open menu if we are editing
    if (this.editingThreadId()) {
      return
    }
    // --- ^^^ END OF ADDED LOGIC ^^^ ---
    this.openThreadMenuId.set(this.openThreadMenuId() === threadId ? null : threadId)
  }

  deleteThread(event: MouseEvent, threadId: string): void {
    event.stopPropagation()
    this.threadToDeleteId.set(threadId)
    this.isConfirmDialogOpen.set(true)
    this.openThreadMenuId.set(null)
  }

  handleConfirmation(wasConfirmed: boolean): void {
    if (wasConfirmed) {
      const threadId = this.threadToDeleteId()
      if (threadId) {
        if (this.chatStore.currentChat().threadId === threadId) {
          this.router.navigate(['/'])
        }
        this.chatStore.deleteThread(threadId)
      }
    }
    this.isConfirmDialogOpen.set(false)
    this.threadToDeleteId.set(null)
  }

  openGlobalContext(): void {
    this.isUserMenuOpen = false 
    this.isGlobalContextModalOpen.set(true)
  }

  handleSaveGlobalContext(context: string): void {
    this.chatStore.saveGlobalContext(context) 
    this.isGlobalContextModalOpen.set(false)
  }

  // --- vvv NEW METHODS FOR RENAMING vvv ---
  
  /**
   * Puts a thread into "edit mode"
   */
  startRename(event: MouseEvent, thread: Thread): void {
    event.stopPropagation()
    this.openThreadMenuId.set(null) // Close the ... menu
    this.editingThreadId.set(thread.id)
    this.editingThreadTitle.set(thread.title)

    // Use setTimeout to wait for Angular to render the input element
    setTimeout(() => {
      const inputElement = document.getElementById(`rename-input-${thread.id}`) as HTMLInputElement
      inputElement?.focus()
      inputElement?.select()
    }, 0)
  }

  /**
   * Handles keyboard events on the rename input
   */
  handleRenameKeydown(event: KeyboardEvent, threadId: string): void {
    if (event.key === 'Enter') {
      event.preventDefault()
      this.saveRename(threadId)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      this.cancelRename()
    }
  }

  /**
   * Saves the new title
   */
  saveRename(threadId: string): void {
    const newTitle = this.editingThreadTitle().trim()
    const originalThread = this.chatStore.threads().find(t => t.id === threadId)

    // Only save if the title is valid and has changed
    if (newTitle && originalThread && newTitle !== originalThread.title) {
      // We assume chatStore.renameThread exists (you'll need to add it)
      this.chatStore.renameThread(threadId, newTitle)
    }
    
    // Exit edit mode regardless
    this.editingThreadId.set(null)
  }

  /**
   * Cancels the edit mode
   */
  cancelRename(): void {
    this.editingThreadId.set(null)
    this.editingThreadTitle.set('')
  }
  // --- ^^^ END OF NEW METHODS ^^^ ---
}