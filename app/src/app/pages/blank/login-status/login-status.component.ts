import { Component, ChangeDetectionStrategy, inject, OnInit } from '@angular/core'
import { OpenIdService } from '../../../services/open-id/open-id.service'
import { UserStore } from '../../../store/user.store'
import { Router } from '@angular/router'

@Component({
  templateUrl: 'login-status.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: 'login-status.component.css',
  providers: [ OpenIdService ],
})
export class LoginStatusComponent implements OnInit {
  openIdService = inject(OpenIdService)
  userStore = inject(UserStore)
  router = inject(Router) 

  ngOnInit(): void {
    setTimeout(() => {
      this.checkAuth()
    }, 2000)
  }

  checkAuth() {
    this.openIdService.oidcSecurityService.checkAuth().subscribe((auth) => {
      if (auth) {
        console.log('auth', auth)
   
        this.userStore.setUser({
          ...auth.userData,
          accessToken: auth.accessToken,
        })

        this.router.navigate(['/'])
      }
    })
  }
}
