import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cafe_pos', '0018_remove_cafetable_x_pos_remove_cafetable_y_pos_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatAssistantSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(default=False)),
                ('bot_name', models.CharField(default='Assistant', max_length=100)),
                ('welcome_message', models.TextField(blank=True, default='Hi! I\'m your assistant. Ask me anything about our menu.')),
                ('custom_instructions', models.TextField(blank=True, help_text='Extra instructions for the AI (e.g. tone, topics to avoid).')),
                ('gemini_api_key', models.CharField(blank=True, max_length=200)),
                ('gemini_model', models.CharField(default='gemini-2.5-flash', max_length=100)),
                ('groq_api_key', models.CharField(blank=True, max_length=200)),
                ('groq_model', models.CharField(default='llama-3.1-8b-instant', max_length=100)),
                ('product_data_json', models.TextField(blank=True, help_text='Auto-generated menu snapshot fed to the AI.')),
                ('last_scraped_at', models.DateTimeField(blank=True, null=True)),
                ('terms_and_conditions', models.TextField(blank=True, help_text='Terms customers must accept before chatting. Leave blank to skip the T&C step.')),
                ('cafe', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='chat_assistant_settings',
                    to='tenants.cafe',
                )),
            ],
            options={
                'verbose_name': 'Chat assistant settings',
                'verbose_name_plural': 'Chat assistant settings',
            },
        ),
        migrations.CreateModel(
            name='ChatSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_token', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('customer_name', models.CharField(blank=True, max_length=150)),
                ('customer_email', models.EmailField(blank=True, max_length=255)),
                ('terms_accepted', models.BooleanField(default=False)),
                ('terms_accepted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('cafe', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='chat_sessions',
                    to='tenants.cafe',
                )),
                ('order', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='chat_sessions',
                    to='cafe_pos.order',
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant')], max_length=10)),
                ('content', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='messages',
                    to='cafe_pos.chatsession',
                )),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
    ]
