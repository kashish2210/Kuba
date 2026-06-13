from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cafe_pos', '0010_merge_0009_alter_order_status_0009_coupon_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='role',
            field=models.CharField(
                choices=[('admin', 'Admin'), ('cashier', 'Cashier'), ('kitchen', 'Kitchen Display')],
                default='cashier',
                max_length=20,
            ),
        ),
    ]
