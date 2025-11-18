kakao.maps.load(function () {
    const container = document.getElementById('map');

    const options = {
        center: new kakao.maps.LatLng(37.5665, 126.9780),
        level: 6
    };

    const map = new kakao.maps.Map(container, options);
});
