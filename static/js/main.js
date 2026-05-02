// Generic helper functions
$(document).ready(function() {
    // Add active class to current nav link
    $('.nav-link').each(function() {
        if (this.href === window.location.href) {
            $(this).addClass('active');
        }
    });
});