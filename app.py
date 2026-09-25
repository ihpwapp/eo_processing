"""Run with: streamlit run app.py"""
from datetime import date, timedelta
import re
import shutil

import folium
from folium.plugins import Draw
from authentication import connect_session, reconnect_job
import functions2
from functions2 import PRODUCTS
import streamlit as st
from streamlit_folium import st_folium

from web_runtime import Run, cleanup, validate_request

st.set_page_config(page_title='Earth Observatory', page_icon='🌍', layout='wide')
st.title('Earth Observatory')
st.caption('Explore Sentinel-2 imagery, vegetation and burn indices for your area.')
cleanup()

with st.sidebar:
    st.header('Copernicus account')
    connected = 'connection' in st.session_state
    if connected:
        st.success('Connected to Copernicus')
    else:
        st.write('Sign in to use your own Copernicus processing quota. Your password stays with Copernicus.')
    if st.button('Reconnect to Copernicus' if connected else 'Sign in with Copernicus', type='primary'):
        instructions = st.empty()
        def display_login(message):
            if 'http' in message:
                # SDK callback is scoped to this session; no stdout interception.
                instructions.info(message)
                urls = re.findall(r'https://[^\s\'\"<>]+', message)
                if urls:
                    st.link_button('Open Copernicus sign-in', urls[0])
        try:
            connection = connect_session(display_login)
            reconnect_job(st.session_state.get('run'), connection)
            st.session_state.connection = connection
            st.rerun()
        except Exception:
            instructions.error('Sign-in expired or failed. Please try again and complete verification within five minutes.')
    if connected and st.button('Sign out'):
        run = st.session_state.get('run')
        try:
            if run and run.active:
                run.cancel()
            if run:
                shutil.rmtree(run.directory, ignore_errors=True)
            del st.session_state.connection
            st.session_state.pop('run', None)
            st.rerun()
        except Exception:
            st.error('Could not stop the active job. Reconnect, then try Cancel before signing out.')
    st.caption('Refreshing the browser may require signing in again. Results are temporary and expire after one hour or a server restart. Keep this tab open while processing.')

run = st.session_state.get('run')
active = bool(run and run.active)
left, right = st.columns([3, 1])
with left:
    m = folium.Map(location=[4.2105, 101.9758], zoom_start=5, tiles='OpenStreetMap')
    Draw(export=False, draw_options={'polyline': False, 'rectangle': False, 'circle': False, 'circlemarker': False, 'marker': False, 'polygon': {'allowIntersection': False}}, edit_options={'edit': True, 'remove': True}).add_to(m)
    drawn = st_folium(m, key='area_map', height=460, use_container_width=True, returned_objects=['all_drawings'])
    st.caption('Draw one polygon. Results will be clipped to its boundary.')
with right:
    st.subheader('Analysis')
    compare = st.checkbox('Compare two periods (B − A)', value=False, disabled=active)
    a_start = st.date_input('Period A start', date.today() - timedelta(days=30), disabled=active, key='period_a_start')
    a_end = st.date_input('Period A end (exclusive)', date.today(), disabled=active, key='period_a_end')
    b_start = b_end = None
    if compare:
        b_start = st.date_input('Period B start', a_end, disabled=active, key='period_b_start')
        b_end = st.date_input('Period B end (exclusive)', date.today(), disabled=active, key='period_b_end')
        st.caption('Comparison runs two jobs per product and computes B − A locally. Expect roughly double the quota and waiting time.')
    available = [p for p in PRODUCTS if p != 'sar'] if compare else list(PRODUCTS)
    selected = [p for p in available if st.checkbox(PRODUCTS[p][0], value=True, key=f'product_{p}', disabled=active)]
    st.caption('False colour highlights vegetation. NDVI and NBR downloads retain their original index values; enhancements affect previews only.')
    if st.button('Run analysis', type='primary', disabled=active or 'connection' not in st.session_state):
        try:
            drawings = (drawn or {}).get('all_drawings') or []
            if len(drawings) != 1:
                raise ValueError('Please leave exactly one polygon on the map.')
            polygon = validate_request(drawings[0]['geometry'], a_start, a_end, selected, b_start, b_end)
            if run:
                shutil.rmtree(run.directory, ignore_errors=True)
            acquisitions = {}
            try:
                acquisitions['A'] = functions2.scene_inventory(polygon, a_start, a_end)
                if b_start is not None:
                    acquisitions['B'] = functions2.scene_inventory(polygon, b_start, b_end)
            except ValueError as exc:
                acquisitions['_error'] = str(exc)
            st.session_state.run = Run(polygon, a_start, a_end, selected, b_start, b_end, acquisitions=acquisitions)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def period_label(phase):
    return {'A': 'Period A', 'B': 'Period B', 'diff': 'Difference (B − A)'}.get(phase, phase)


def show_result(run, product, phase):
    result = run.results.get((product, phase))
    if result is None:
        return
    if phase != 'A' or run.compare:
        st.markdown(f'**{period_label(phase)}**')
    if not result.preview.exists():
        st.info('This result has expired. Run the analysis again to regenerate it.')
        return
    st.image(str(result.preview), use_container_width=True)
    for path in [result.preview, *result.rasters]:
        if path.exists():
            st.download_button(f'Download {path.name}', data=path.read_bytes(), file_name=path.name, key=f'{run.directory.name}_{product}_{phase}_{path.name}')


def show_acquisitions(run):
    if not run.acquisitions:
        return
    if '_error' in run.acquisitions:
        st.caption(run.acquisitions['_error'])
        return
    for label in ('A', 'B'):
        scenes = run.acquisitions.get(label)
        if not scenes:
            continue
        st.markdown(f'**Acquisition dates · period {label}**')
        st.dataframe([{
            'Acquisition time': scene.datetime,
            'Cloud cover (%)': round(scene.cloud_cover, 2),
            'Platform': scene.platform,
        } for scene in scenes], use_container_width=True)


@st.fragment(run_every=5)
def results_panel():
    cleanup()
    run = st.session_state.get('run')
    if run is None:
        st.info('Sign in, draw an area and choose your analysis to begin.')
        return
    was_active = run.active
    if run.active:
        if st.button('Cancel analysis'):
            try:
                run.cancel()
                st.rerun()
            except Exception:
                st.error('Cancellation could not be confirmed. Please retry.')
        try:
            run.tick(st.session_state.connection)
        except Exception:
            st.error('Could not update processing. Retry cancellation or wait for the next status check.')
    st.progress(run.index / len(run.stages), text=run.status)
    if run.job is not None:
        st.caption(f'Copernicus job: {run.job.job_id}')
    for (product, phase), message in run.errors.items():
        st.error(f'{PRODUCTS[product][0]} · {period_label(phase)}: {message}')
    for product in run.products:
        if not any((product, phase) in run.results for phase in ('A', 'B', 'diff')):
            continue
        st.subheader(PRODUCTS[product][0])
        show_result(run, product, 'A')
        if run.compare:
            show_result(run, product, 'B')
            show_result(run, product, 'diff')
    if run.compare:
        st.divider()
    show_acquisitions(run)
    if was_active and not run.active:
        st.rerun()


results_panel()