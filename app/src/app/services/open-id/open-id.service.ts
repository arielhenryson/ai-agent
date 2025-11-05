import { Injectable, inject } from '@angular/core'
import { OidcSecurityService } from 'angular-auth-oidc-client'


@Injectable(
  {
    providedIn: 'root',
  },
)
export class OpenIdService {
  oidcSecurityService = inject(OidcSecurityService)

  signIn() {
    this.oidcSecurityService.authorize()
  }

  signOut() {
    this.oidcSecurityService.logoff()
      .subscribe(result => console.log(result))
  }
}