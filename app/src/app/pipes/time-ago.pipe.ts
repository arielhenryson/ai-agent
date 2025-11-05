// src/app/pipes/time-ago.pipe.ts

import { Pipe, PipeTransform, OnDestroy, ChangeDetectorRef, NgZone, inject } from '@angular/core'

@Pipe({
  name: 'timeAgo',
  standalone: true,
  pure: false,
})
export class TimeAgoPipe implements PipeTransform, OnDestroy {
  private timer: number | null = null

  changeDetectorRef = inject(ChangeDetectorRef)
  ngZone = inject(NgZone)

  transform(value: Date | string | number): string {
    this.removeTimer() 

    if (!value) {
      return ''
    }

    const date = new Date(value)
    const now = new Date()
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

    this.setTimer(seconds)

    // MODIFICATION HERE: Changed the threshold from 30 to 60 seconds
    if (seconds < 60) {
      return 'Just now'
    }

    const intervals: Record<string, number> = {
      year: 31536000,
      month: 2592000,
      week: 604800,
      day: 86400,
      hour: 3600,
      minute: 60,
    }

    let counter
    for (const intervalName in intervals) {
      counter = Math.floor(seconds / intervals[intervalName])
      if (counter > 0) {
        if (counter === 1) {
          return `${counter} ${intervalName} ago` // singular
        } else {
          return `${counter} ${intervalName}s ago` // plural
        }
      }
    }
    return `${Math.floor(seconds)} seconds ago`
  }

  ngOnDestroy(): void {
    this.removeTimer()
  }

  private setTimer(seconds: number): void {
    const updateInterval = this.getUpdateInterval(seconds)
    if (updateInterval === -1) {
        return // No need to set a timer for very old dates
    }

    this.ngZone.runOutsideAngular(() => {
      this.timer = window.setInterval(() => {
        this.ngZone.run(() => {
          this.changeDetectorRef.markForCheck()
        })
      }, updateInterval)
    })
  }

  private removeTimer(): void {
    if (this.timer) {
      window.clearInterval(this.timer)
      this.timer = null
    }
  }

  private getUpdateInterval(seconds: number): number {
    const minute = 60
    const hour = minute * 60
    const day = hour * 24

    if (seconds < minute) {
      return 5000 // Update every 5 seconds for the first minute
    } else if (seconds < hour) {
      return 30000 // Update every 30 seconds for the first hour
    } else if (seconds < day) {
      return 3600000 // Update every hour for the first day
    } else {
      return -1 // No need to update after a day
    }
  }
}