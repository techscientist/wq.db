from wq.db.rest import app
from .models import RootModel, UserManagedModel
app.router.register_model(RootModel, url="")
app.router.register_model(UserManagedModel)
app.router.set_extra_config(debug=True)