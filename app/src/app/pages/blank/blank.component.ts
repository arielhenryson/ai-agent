import { Component, ChangeDetectionStrategy } from '@angular/core'
import { RouterOutlet } from '@angular/router'

@Component({
  templateUrl: 'blank.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ RouterOutlet ],
})
export class BlankComponent {}