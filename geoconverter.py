import csv
import json
import os
import pandas as pd
from flask import Flask, flash, render_template, request
from flask import redirect, url_for, send_file
from werkzeug.utils import secure_filename
import folium


app = Flask(__name__)

# upload folder for files, here aws lambda /tmp/
UPLOAD_FOLDER = '/tmp/'
OUTPUTFILE = 'output.geojson'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# list of allowed file extensions
ALLOWED_EXTENSIONS = set(['txt', 'csv'])

def allowed_file(filename):
    """
    check if file extension of uploaded file is in 
    ALLOWED_EXTENSIONS

    keywords:
    content -- content of uploaded file
    """

    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def sniff_delimiter_from_content(content):
    """
    use csv sniffer to check for delimiter

    keywords:
    content -- content of uploaded file
    """

    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(content.read(2048).decode('utf8'))
    except UnicodeDecodeError:
        dialect = sniffer.sniff(content.read(2048).decode('latin1'))
    return dialect.delimiter


def sniff_header_from_content(content):
    """
    use csv sniffer to check if content has a header 
    including column names

    keywords:
    content -- content of uploaded file
    """

    content.seek(0)
    sniffer = csv.Sniffer()
    try:
        has_header = sniffer.has_header(content.read(2048).decode('utf8'))
    except UnicodeDecodeError:
        has_header = sniffer.has_header(content.read(2048).decode('latin1'))
    return has_header


def dataframe_from_content(content, delimiter, has_header):
    """
    create a pandas dataframe from uploaded content

    keywords:
    content -- uploaded file
    delimiter -- delimiter from sniffer
    has_header -- True/False content has header
    """

    if has_header:
        try:
            df = pd.read_csv(content, sep=delimiter)
            return df
        except UnicodeError:
            df = pd.read_csv(content, sep=delimiter, encoding='latin1')
            return df
    else:
        return False


def create_geojson_from_df(df):
    """
    create and dump geojson from pandas dataframe
    including coordinates and columns as properties.
    http://geoffboeing.com/2015/10/exporting-python-data-geojson/

    keyword:
    df -- pandas dataframe
    """

    try:
        properties = df.copy().drop(['lat', 'lon'], axis=1).columns.tolist()
        geojson = {'type': 'FeatureCollection', 'features': []}

        for _, row in df.iterrows():
            feature = {'type': 'Feature',
                       'properties': {},
                       'geometry': {'type': 'Point', 'coordinates': []}}
            feature['geometry']['coordinates'] = [row['lon'], row['lat']]
            for prop in properties:
                feature['properties'][prop] = row[prop]
            geojson['features'].append(feature)
        
        with open(os.path.join(app.config['UPLOAD_FOLDER'], OUTPUTFILE), 'w', encoding='utf8') as fp:
             json.dump(geojson, fp, ensure_ascii=False)
        
        return geojson
        #return send_file(os.path.join(app.config['UPLOAD_FOLDER'], OUTPUTFILE), as_attachment=True)

    except KeyError:
        return "The file you uploaded does not have 'lat' and/or 'lon' columns"


def create_map_from_geojson(geojson, df):
    """
    create a folium map to be served via iframe in url_for('mapviewer')

    keywords:
    df -- dataframe of uploaded delimited file
    geojson -- geojson object created from dataframe
    """

    m = folium.Map(
        location=[df.lat.mean(), df.lon.mean()],
        zoom_start=6)
    folium.GeoJson(geojson, name='geojson').add_to(m)
    mapname = 'map.html'
    m.save(os.path.join(app.config['UPLOAD_FOLDER'], mapname))
    

@app.route('/transform/<filename>', methods=['GET', 'POST'] )
def transformed_file(filename):
    f = filename
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f)

    with open(os.path.join(app.config['UPLOAD_FOLDER'], f) , 'rb') as content:
        delimiter = sniff_delimiter_from_content(content)
        has_header = sniff_header_from_content(content)
        df = dataframe_from_content(filepath, delimiter, has_header)
    
    try:
        if not df:
            return "The file you uploaded does not contain column-headers"
        else:
            geojson = create_geojson_from_df(df)
    except ValueError:
        geojson = create_geojson_from_df(df)
    
    create_map_from_geojson(geojson, df)
    
    return render_template('download.html')


@app.route("/download/", methods=['GET'])
def download_geojson():
    return send_file(os.path.join(
        app.config['UPLOAD_FOLDER'], OUTPUTFILE), as_attachment=True)


@app.route("/mapviewer/")
def map_viewer():
    fp = os.path.join(app.config['UPLOAD_FOLDER'], 'map.html')
    with open(fp, "r") as fo:
        html_contents = fo.read()
    return html_contents


@app.route('/', methods=['GET', 'POST'])
def upload_file():
    
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(url_for('upload_file'))
        file = request.files['file']

        # if user does not select file, browser also
        # submit a empty part without filename

        if file.filename == '':
            flash('No selected file')
            return redirect(url_for('upload_file'))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            return redirect(url_for('transformed_file', filename=filename))
    
    # Render file input form
    return render_template('convert.html')

if __name__ == '__main__':
    app.run()
