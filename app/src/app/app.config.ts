import { ApplicationConfig, provideBrowserGlobalErrorListeners, provideZonelessChangeDetection, isDevMode } from '@angular/core'
import { provideRouter, withComponentInputBinding } from '@angular/router'
import { provideHttpClient } from '@angular/common/http'   // 👈 add this
import { provideAuth, LogLevel } from 'angular-auth-oidc-client'

import { routes } from './app.routes'
import { sharedConfig } from './config'
import { provideServiceWorker } from '@angular/service-worker'
import { ApiService } from './services/api/api.service'
import { provideMarkdown } from 'ngx-markdown'

export const appConfig: ApplicationConfig = {
  providers: [
    ApiService,
    provideBrowserGlobalErrorListeners(),
    provideZonelessChangeDetection(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(),
    provideAuth({
      config: {
        authority: sharedConfig.openIDAuthority,
        redirectUrl: window.location.origin + '/login-status',
        postLogoutRedirectUri: window.location.origin,
        clientId: sharedConfig.openIDClientID,
        scope: 'openid profile email',
        responseType: 'code',
        silentRenew: true,
        useRefreshToken: true,
        logLevel: LogLevel.Debug,
        customParamsAuthRequest: {
          audience: 'https://dev-qd64wbsipbt3podg.us.auth0.com/api/v2/',
        },
      },
    }), 
    provideServiceWorker('ngsw-worker.js', {
            enabled: !isDevMode(),
            registrationStrategy: 'registerWhenStable:30000'
    }),
    provideMarkdown(),
  ]
}
