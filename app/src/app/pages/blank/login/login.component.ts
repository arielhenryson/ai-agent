import { Component, ChangeDetectionStrategy, inject } from '@angular/core'
import { OpenIdService } from '../../../services/open-id/open-id.service'

@Component({
  templateUrl: 'login.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [OpenIdService],
})
export class LoginComponent {
  openIdService = inject(OpenIdService) 

  async login() {
    this.openIdService.signIn()
  }
}
