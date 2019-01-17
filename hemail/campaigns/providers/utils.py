from typing import Tuple


def get_email_parts(email: str) -> Tuple[str, str]:
    return tuple(email.rsplit('@', 1))


def get_email_domain(email: str) -> str:
    return get_email_parts(email)[1]


def get_email_local_path(email: str) -> str:
    return get_email_parts(email)[0]


def get_default_sender_name(user) -> str:
    return (' '.join(filter(bool, [user.first_name, user.last_name])) or user.username).strip()


def get_default_signature(user) -> str:
    return 'Regards, %s' % get_default_sender_name(user)
