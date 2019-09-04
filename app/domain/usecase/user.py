from datetime import datetime, timedelta
from typing import List, Set

import jwt

from app.domain import validator
from app.pkgs import errors
from app.domain.model.user import User
from app.infrastructure.persistence.user import UserRepository
from app.infrastructure.persistence.access_policy import AccessPolicyRepository
from app.infrastructure.persistence.blacklist_token import BlacklistTokenRepository
from app.pkgs.type_check import type_check
from app.pkgs.time import time_to_int


class UserService(object):

    def __init__(self, user_repo: UserRepository, access_blacklist: AccessPolicyRepository,
                 blacklist_token_repo: BlacklistTokenRepository, public_key: str, secret_key=''):
        self.user_repo: UserRepository = user_repo
        self.access_policy_repo = access_blacklist
        self.blacklist_token_repo = blacklist_token_repo
        self.secret_key = secret_key
        self.public_key = public_key

    def validate_user_email_password(self, email: str, password: str):
        validator.validate_email(email)
        validator.validate_password(password)
        current_user = self.user_repo.count_by_email(email)
        if current_user > 0:
            raise errors.email_already_exist

    def create_new_user(self, email: str, password: str):
        email = email.lower()
        self.validate_user_email_password(email, password)
        user = User(email=email, password=password)
        user.hash_password(password)
        # set is_confirm to true
        user.is_confirmed = True
        return self.user_repo.create(user)

    def sign_up_new_user(self, email: str, password: str):
        self.validate_user_email_password(email, password)
        user: User = User(email=email, password=password)
        user.hash_password(password)
        # set is_confirm to False
        user.is_confirmed = False
        return self.user_repo.create(user)

    def login(self, email: str, password: str):
        validator.validate_email(email)
        user, roles, permissions = self.user_repo.find_user_for_auth(email)
        if user:
            if user.verify_password(password):
                role_ids = []
                for r in roles:
                    role_ids.append(r.id)
                permissions_name: Set[str] = set()
                for p in permissions:
                    permissions_name.add(p.permission)
                other_info = {
                    'user': {
                        'id': user.id,
                        'email': user.email,
                        'is_confirmed': user.is_confirmed
                    },
                    'role_ids': role_ids,
                    'permissions': list(permissions_name)
                }
                token = self.encode_auth_token(user, other_payload_info=other_info)
                # create and return token here
                return {'token': token.decode("utf-8")}
            else:
                raise errors.password_verifying_failed
        raise errors.email_cannot_be_found

    def logout(self, auth_token: str):
        t = self.blacklist_token_repo.add_token(auth_token)
        return f'logout at: {t.blacklisted_on}'

    def find_by_id(self, user_id: int):
        validator.validate_id(user_id)
        user = self.user_repo.find(user_id)
        if user:
            return user
        raise errors.record_not_found

    def find_all_user_info_by_id(self, user_id: int):
        validator.validate_id(user_id)
        user, roles, permissions = self.user_repo.find_all_user_info_by_id(user_id)
        user.roles = roles
        if user:
            return user, permissions
        raise errors.record_not_found

    def search(self, email: str) -> List[dict]:
        users = self.user_repo.search(email)
        return users

    @type_check
    def update_password(self, user_id: int, old_password: str, new_password: str, retype_password: str):
        if new_password == retype_password:
            raise errors.Error(
                'New Password and retype password is not matched')
        validator.validate_password(new_password)
        user = self.find_by_id(user_id)
        if not user:
            raise errors.record_not_found
        if user.verify_password(old_password):
            # confirm old password
            user.hash_password(new_password)
            user = self.user_repo.update(user)
            self.access_policy_repo.change_user(user, note=f'update user password')
        return user

    @type_check
    def update_is_confirmed(self, user_id: int, is_confirmed: bool):
        user = self.find_by_id(user_id)
        if not user:
            raise errors.record_not_found
        user.is_confirmed = is_confirmed
        user = self.user_repo.update(user)
        self.access_policy_repo.change_user(user, note=f'update user is_confirmed = {user.is_confirmed}')
        return user

    def is_accessible(self, user_id: int, role_ids: List[int], token_iat_int: int):
        checker = self.access_policy_repo.find_for_token_validation(user_id, role_ids)
        # print(checker.to_json(), time_to_int(checker.denied_before), token_iat_int)
        if checker is None:
            return True, 'ok'
        if time_to_int(checker.denied_before) > token_iat_int:
            return False, checker.note
        return True, 'ok'

    def delete(self, user_id: int):
        validator.validate_id(user_id)
        user = self.user_repo.delete(user_id)
        self.access_policy_repo.change_user(user, note='delete user')
        return user

    def encode_auth_token(self, user: User, other_payload_info: dict):
        """
        Generates the Auth Token
        :return: string
        """
        try:
            payload = {
                'exp': datetime.utcnow() + timedelta(hours=72, seconds=5),
                'iat': datetime.utcnow(),
                'sub': user.id,
            }
            payload.update(other_payload_info)
            return jwt.encode(
                payload,
                self.secret_key,
                algorithm='RS256'
            )
        except Exception as e:
            raise e

    def validate_auth_token(self, auth_token):
        """
        Validates the auth token and check blacklist token
        :param auth_token:
        :return: integer|string as user_id or error string
        """
        try:
            payload: dict = jwt.decode(
                auth_token, self.public_key, algorithms=['RS256'])
            is_blacklisted_token = self.blacklist_token_repo.is_blacklist(auth_token)
            if is_blacklisted_token:
                raise errors.token_blacklisted
            else:
                return payload
        except jwt.ExpiredSignatureError:
            raise errors.token_expired
        except jwt.InvalidTokenError:
            raise errors.invalid_token
