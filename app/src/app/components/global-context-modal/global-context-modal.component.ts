import { Component, EventEmitter, Input, Output, signal } from '@angular/core'
import { CommonModule } from '@angular/common'
import { FormsModule } from '@angular/forms'

@Component({
  selector: 'app-global-context-modal',
  imports: [CommonModule, FormsModule],
  templateUrl: './global-context-modal.component.html',
})
export class GlobalContextModalComponent {
  @Input() set initialContext(context: string) {
    this.contextContent.set(context)
  }
  // RENAMED: from 'close' to 'closeRequested'
  @Output() closeRequested = new EventEmitter<void>()
  // RENAMED: from 'save' to 'saveContext'
  @Output() saveContext = new EventEmitter<string>()

  contextContent = signal('')

  // RENAMED: from 'onClose' to 'onCloseRequested'
  onCloseRequested(): void {
    this.closeRequested.emit()
  }

  // RENAMED: from 'onSave' to 'onSaveContext'
  onSaveContext(): void {
    this.saveContext.emit(this.contextContent())
  }
}