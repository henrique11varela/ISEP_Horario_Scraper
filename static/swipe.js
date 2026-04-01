const bod = document.querySelector("body")
bod.addEventListener("touchstart", (event) => {
    const start = event.changedTouches[0].clientX
    function endFunc(event2) {
        let pathArray = window.location.pathname.split('/')
        const end = event2.changedTouches[0].clientX
        if (end - start < -100) {
            day = (Number(pathArray.at(-1)) + 1) % 7
            navigation.navigate(`/${pathArray.at(-2)}/${day}`)
        }
        else if (end - start > 100) {
            day = (Number(pathArray.at(-1)) - 1) % 7
            if (day < 0) {
                day = 6
            }
            navigation.navigate(`/${pathArray.at(-2)}/${day}`)
        }
        bod.removeEventListener("touchend", endFunc)    
    }
    bod.addEventListener("touchend", endFunc)
})
