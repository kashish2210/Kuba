from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cafe_pos', '0008_alter_product_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='coupon',
            name='name',
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
