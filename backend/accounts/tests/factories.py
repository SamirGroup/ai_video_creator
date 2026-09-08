from __future__ import annotations

import factory

from accounts.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"creator{n}@example.com")
    full_name = factory.Faker("name")
    is_email_verified = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        raw_password = extracted or "correct-horse-battery-staple"
        self.set_password(raw_password)
        if create:
            self.save(update_fields=["password"])
