########################################################################

# Enable importing `shared` from the parent directory
import sys, os

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(root_dir)

########################################################################


import queue
import threading
import RPi.GPIO as GPIO
import lock
import camera
import numpad
import heartbeat
import reporting
from shared import EventType, ISODateTime


def process_event(type, data):
    print(f"Got event: type {type}, data {data}")

    # This type can only come from device
    # data is the a base64 string containing image data
    if type == EventType.MailboxIncomingMail:
        return (EventType.MailboxIncomingMail, data)

    # This type can only come from device
    # data is the password input (can be empty, which means lock)
    if type == EventType.MailboxNumPadInput:
        if not data:
            lock.lock_close()
            return (
                EventType.MailboxLocked,
                "You have locked your mailbox via numpad input.",
            )
        elif lock.verify_password(data):
            lock.lock_open()
            return (
                EventType.MailboxUnlocked,
                "You have unlocked your mailbox via numpad input.",
            )
        elif lock.need_raise_alert():
            return (
                EventType.MailboxSecurityAlert,
                "Multiple consecutive failed attempts to unlock the mailbox via numpad detected, which may indicate attempt of unauthorized access.",
            )

    # This type can only come from heartbeat
    # data is the new password
    if type == EventType.MailboxPasswordChanged:
        lock.reset_password(data)
        return (
            EventType.MailboxPasswordChanged,
            "You have changed your mailbox password via the dashboard.",
        )

    # These two types can only come from heartbeat
    if type == EventType.MailboxUnlocked:
        lock.lock_open()
        return (
            EventType.MailboxUnlocked,
            "You have unlocked your mailbox via the dashboard.",
        )
    if type == EventType.MailboxLocked:
        lock.lock_close()
        return (
            EventType.MailboxUnlocked,
            "You have locked your mailbox via the dashboard.",
        )


def main():
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Event flag to signal daemons/workers to stop
        interrupt = threading.Event()
        # Message queue to accept events generated by daemons
        message_queue = queue.Queue()
        # Message queue to pass data reporting task to worker thread
        report_queue = queue.Queue()

        # Init modules
        lock.init()
        reporting.init(interrupt, report_queue)
        numpad.init(interrupt, message_queue)
        camera.init(interrupt, message_queue)
        heartbeat.init(interrupt, message_queue)

        # Main event loop
        while not interrupt.is_set():
            try:
                # Will block until an event is in the queue
                (type, data) = message_queue.get()
                # Process event and get report
                report = process_event(type, data)
                # If event not recognized or nothing to report, skip
                if not report:
                    continue
                # Add timestamp and put into report queue
                time = ISODateTime.now()
                (type, data) = report
                time = str(time)
                report_queue.put({"type": type, "time": time, "data": data})
            except Exception as e:
                print(f"Unexpected error when processing: {e}")

    except KeyboardInterrupt:
        interrupt.set()

    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
