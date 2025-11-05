// src/app/store/user.store.ts
import { signalStore, withMethods, withState, patchState } from '@ngrx/signals'

/**
 * Interface representing a user.
 */
interface User {
  id: string
  email: string
  name: string
  accessToken: string
}

/**
 * Interface for the entire user state, including user info and settings.
 */
interface UserState {
  user: User | undefined
}

/**
 * The initial state for the user store.
 */
const initialState: UserState = {
  user: undefined,
}

export const UserStore = signalStore(
  { providedIn: 'root' },
  withState(initialState),
  withMethods((
    store, 
  ) => ({
    async setUser(user: User | undefined) {
      patchState(store, { user })
    },  
  })),
)