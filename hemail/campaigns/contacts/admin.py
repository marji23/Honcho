from django.contrib import admin

from .models import Contact, ContactList, Note


class NoteInline(admin.StackedInline):
    model = Note
    extra = 0
    show_change_link = True


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = (
        'email', 'first_name', 'last_name', 'phone_number', 'blacklisted', 'zip_code',
    )

    inlines = [NoteInline, ]


@admin.register(ContactList)
class ContactListAdmin(admin.ModelAdmin):
    list_display = (
        'name',
    )
    filter_vertical = ('contacts',)


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'topic', 'author', 'created', 'private')
    list_filter = ('topic', 'author', 'created', 'private')
