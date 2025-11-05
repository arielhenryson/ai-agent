import { Component, EventEmitter, Input, OnInit, Output, OnDestroy } from '@angular/core'
import { CommonModule } from '@angular/common'

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './confirm-dialog.component.html',
})
export class ConfirmDialogComponent implements OnInit, OnDestroy {
  @Input() title = 'Confirm Action'
  @Input() message = 'Are you sure you want to proceed?'
  @Input() confirmText = 'Confirm'

  ngOnInit(): void {
    document.body.classList.add('no-scroll')
  }

  ngOnDestroy(): void {
    document.body.classList.remove('no-scroll')
  } 
  
  @Output() confirmed = new EventEmitter<boolean>()

  onConfirm(): void {
    this.confirmed.emit(true)
  }

  onCancel(): void {
    this.confirmed.emit(false)
  }
}