import { Injectable, inject } from '@angular/core'
import { UserStore } from '../../store/user.store'
import { Router } from '@angular/router' // Import the Router

/**
 * Service to handle all authenticated API calls using the user's access token.
 * It provides reusable wrappers around the native fetch API.
 */
@Injectable({
  providedIn: 'root',
})
export class ApiService {
  userStore = inject(UserStore)
  router = inject(Router) // Inject the Router

  private getAuthHeaders(contentType: 'json' | 'none' = 'none'): HeadersInit {
    const headers: HeadersInit = {
      Authorization: `Bearer ${this.userStore.user()?.accessToken}`,
    }

    if (contentType === 'json') {
      headers['Content-Type'] = 'application/json'
    }

    return headers
  }

  /**
   * General request handler that fetches, checks status, and parses JSON.
   * @param url The API endpoint URL.
   * @param options Fetch RequestInit options.
   * @returns A promise resolving to the parsed JSON response of type T.
   */
  private async request<T>(url: string, options: RequestInit = {}): Promise<T> {
    let response: Response

    try {
      // Wait for the fetch request to complete
      response = await fetch(url, options)
    } catch (error) {
      // This block catches network errors (e.g., server down, CORS, DNS issue)
      console.error('Network error or fetch failed:', error)

      // Clear the user session
      this.userStore.setUser(undefined)
      // Navigate to the login page
      this.router.navigate(['/login'])

      // Throw an error to stop further execution in the calling function
      throw new Error('Network error. Redirecting to login.')
    }

    // Check if the response was not successful (e.g., 4xx, 5xx status)
    if (!response.ok) {
      // Check for specific authentication/authorization errors
      if (response.status === 401 || response.status === 403) {
        console.error('Authentication error. Redirecting to login.')

        // Clear the user session
        this.userStore.setUser(undefined)
        // Navigate to the login page
        this.router.navigate(['/login'])

        throw new Error('Authentication error. Redirecting to login.')
      }

      // Handle other HTTP errors (like 400, 404, 500) as before
      let errorMessage = `HTTP error ${response.status}: Failed request to ${url}`
      try {
        const errorBody = await response.json()
        if (errorBody && errorBody.message) {
          errorMessage = errorBody.message
        }
      } catch (e) {
        // ignore if parsing error body fails
      }
      throw new Error(errorMessage)
    }

    // All API responses are expected to be JSON, unless status is 204
    if (response.status === 204) {
      return {} as T
    }
    return (await response.json()) as T
  }

  /**
   * Executes an authenticated GET request.
   */
  get<T>(url: string): Promise<T> {
    console.log(`API GET: ${url}`)

    return this.request<T>(url, {
      headers: this.getAuthHeaders(),
    })
  }

  /**
   * Executes an authenticated POST request with a JSON body.
   */
  post<T>(url: string, body: any): Promise<T> {
    console.log(`API POST: ${url}`)

    return this.request<T>(url, {
      method: 'POST',
      headers: this.getAuthHeaders('json'),
      body: JSON.stringify(body),
    })
  }

  // --- vvv NEW METHOD vvv ---
  /**
   * Executes an authenticated PATCH request with a JSON body.
   */
  patch<T>(url: string, body: any): Promise<T> {
    console.log(`API PATCH: ${url}`)

    return this.request<T>(url, {
      method: 'PATCH',
      headers: this.getAuthHeaders('json'),
      body: JSON.stringify(body),
    })
  }
  // --- ^^^ END OF NEW METHOD ^^^ ---

  /**
   * Executes an authenticated DELETE request.
   */
  delete<T>(url: string): Promise<T> {
    console.log(`API DELETE: ${url}`)

    return this.request<T>(url, {
      method: 'DELETE',
      headers: this.getAuthHeaders(),
    })
  }
}